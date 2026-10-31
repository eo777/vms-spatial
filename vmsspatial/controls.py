"""Control texts in the manuscript's layout.

Three families, each typeset into the manuscript's 4,130 lines in Path 1 order so that the same spatial scorer runs on
all of them with the same page geometry:
    generator streams    saved self-citation runs (``data/controls/streams``), line-aligned to the manuscript
    Markov chains        word-bigram samplers trained on the manuscript (whole; Currier A and B separately; each section
                         separately), each line filled to the manuscript line's character budget; no chain consults
                         position, line, page or geometry
    natural prose        the reference texts (``data/controls/texts``): each line filled to the manuscript line's
                         character budget, or the text's own printed lines placed one per manuscript line slot

THE RULE (PITFALLS 4 and 7). A control's words are laid by character position into the manuscript's line frames at the
line's letter size (``geometry.synthetic_geometry``), and ``build_control`` checks the result (``check_typesetting``: box
width off by 1.5x in under 1 percent of words). A control is never made by dropping its words into the recorded
rectangles of the manuscript words they replace: a box then has the width of another word, and every distance-weighted
pool reads that width. The ``markov_box`` and ``prose_box`` kinds do exactly that; they exist only as flagged
diagnostics of the error (geometry_kind 'recorded', a warning, a caveat in the bundle) and are never a default.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from . import paths
from .geometry import fill_slots, label_like_slot, line_frames, synthetic_geometry

# key: (label, [manifest keys of the seeds])
STREAMS = {
    'timm': ('Original Timm (page draw)', ['controls/streams/m_timm/generated_text.txt'] + ['controls/streams/timm_native_seed%d.json.gz' % s for s in (2, 3, 4, 5)]),
    'noinnov_far0': ('Hooks on the page window, no innovator (far 0)', ['controls/streams/n_noinnov_far0%s/generated_text.txt' % s for s in ('', '_s2', '_s3')]),
    'timm_spatial': ('Original Timm, sources from the words in view (spatial)', ['controls/streams/p_timm_spatial%s/generated_text.txt' % s for s in ('', '_s2', '_s3')]),
    'noinnov_spatial': ('Hooks on the words in view, no innovator (spatial, far 0)', ['controls/streams/p_noinnov_spatial%s/generated_text.txt' % s for s in ('', '_s2', '_s3')]),
    'far0_spatial': ('Governed + innovator, sources from the words in view (spatial, far 0)', ['controls/streams/p_far0_spatial%s/generated_text.txt' % s for s in ('', '_s2', '_s3')]),
}

TEXTS = {
    'la_macer_milan1482': 'controls/texts/la_macer_milan1482.txt',
    'la_psapuleius1543': 'controls/texts/la_psapuleius1543.txt',
    'la_galen_simplicium': 'controls/texts/la_galen_simplicium.txt',
    'la_dioscorides_longob': 'controls/texts/la_dioscorides_longob.txt',
    'la_rhazes_almansor': 'controls/texts/la_rhazes_almansor.txt',
    'la_hildegard_physica': 'controls/texts/la_hildegard_physica.txt',
    'la_vulgate_train': 'controls/texts/la_vulgate_train.txt',
    'de_gart_augsburg1487': 'controls/texts/de_gart_augsburg1487.txt',
    'mhg_train': 'controls/texts/mhg_train.txt',
    'ita_train': 'controls/texts/ita_train.txt',
}
PROSE = ('la_galen_simplicium', 'la_dioscorides_longob', 'la_rhazes_almansor', 'la_hildegard_physica', 'de_gart_augsburg1487')


# ---- generator streams
def read_lines_txt(p) -> List[List[str]]:
    return [l.split() for l in Path(p).read_text(encoding='utf-8-sig').splitlines() if l.strip() and not l.startswith('#')]


def read_stream(key_or_path, n_lines=4130) -> List[List[str]]:
    """A line-aligned text: a manifest key or a path to generated_text.txt / a {'lines': [...]} json(.gz)."""
    p = Path(key_or_path)
    if not p.is_file():
        p = paths.resolve(str(key_or_path))
    if p.suffix == '.gz':
        return json.loads(gzip.decompress(p.read_bytes()))['lines'][:n_lines]
    if p.suffix == '.json':
        return json.loads(p.read_text(encoding='utf-8'))['lines'][:n_lines]
    return read_lines_txt(p)[:n_lines]


def stream_seeds(key, max_seeds=None):
    label, srcs = STREAMS[key]
    return [read_stream(s) for s in srcs[:max_seeds]]


def available_streams() -> Dict[str, List[str]]:
    return {k: [s for s in v[1] if paths.resolve(s, required=False)] for k, v in STREAMS.items()}


# ---- natural prose
def ref_words(key_or_path, limit=60000) -> List[str]:
    p = Path(key_or_path)
    if not p.is_file():
        p = paths.resolve(TEXTS.get(str(key_or_path), str(key_or_path)))
    text = unicodedata.normalize('NFKC', p.read_text(encoding='utf-8', errors='ignore').lower())
    return re.findall(r"[^\W\d_]+", text)[:limit]


def laid_in(ms, words, rng=None, page_sizes=None, start=None):
    """Diagnostic only (PITFALLS 4): one word per manuscript word, a stretch of the text cut into the manuscript's lines
    with the same word count per line, so that the recorded rectangles can be reused. Returns (lines, start). A text's value is passage-sensitive, so pass
    `start` to reproduce a passage, or record the returned start."""
    page_sizes = page_sizes or ms.page_sizes()
    total = sum(page_sizes)
    if len(words) < total + 10:
        raise ValueError('text too short: %d words for %d slots' % (len(words), total))
    if start is None:
        start = int((rng or np.random.default_rng(20261027)).integers(0, len(words) - total))
    seq = words[start:start + total]
    out, at = [], 0
    for p, sz in zip(ms.pages, page_sizes):
        pt = seq[at:at + sz]
        at += sz
        k = 0
        for l in range(p['start_line'], p['end_line']):
            n = len(ms.lines[l]['words'])
            out.append(pt[k:k + n])
            k += n
    return out, start


def fill_by_chars(ms, words, rng=None, start=None):
    """Each manuscript line filled to its own character budget (at least one word) from a start offset; synthetic
    rectangles follow (geometry.synthetic_geometry). Returns (lines, start)."""
    need = sum(L['chars'] for L in ms.lines) // 4 + 10
    if start is None:
        start = int((rng or np.random.default_rng(20261027)).integers(0, max(1, len(words) - need)))
    seq = words[start:]
    out, at = [], 0
    for L in ms.lines:
        cap = L['chars']
        if at >= len(seq):
            raise ValueError('text too short for the character-budget fill: %d words from offset %d; pass a longer text or an earlier --start' % (len(words), start))
        line = [seq[at]]
        used = len(seq[at])
        at += 1
        while at < len(seq) and used + 1 + len(seq[at]) <= cap:
            line.append(seq[at])
            used += 1 + len(seq[at])
            at += 1
        out.append(line)
    if at >= len(seq):
        raise ValueError('text too short for the character-budget fill')
    return out, start


def native_lines(key_or_path, wrap_factor=1.6) -> List[List[str]]:
    """A printed text's own lines: OCR fragments (one token of at most two letters) dropped, over-long lines broken at
    word boundaries."""
    p = Path(key_or_path)
    if not p.is_file():
        p = paths.resolve(TEXTS.get(str(key_or_path), str(key_or_path)))
    text = unicodedata.normalize('NFKC', p.read_text(encoding='utf-8', errors='ignore').lower())
    raw = []
    for line in text.splitlines():
        ws = re.findall(r"[^\W\d_]+", line)
        if not ws or (len(ws) == 1 and len(ws[0]) <= 2):
            continue
        raw.append(ws)
    med = np.median([sum(len(w) for w in ws) + len(ws) - 1 for ws in raw])
    limit = int(wrap_factor * med)
    out = []
    for ws in raw:
        if sum(len(w) for w in ws) + len(ws) - 1 <= limit:
            out.append(ws)
            continue
        cur, used = [], 0
        for w in ws:
            if cur and used + 1 + len(w) > med:
                out.append(cur)
                cur, used = [], 0
            cur.append(w)
            used += len(w) + (1 if used else 0)
        if cur:
            out.append(cur)
    return out


def native_layout(ms, app, lines, rng, start=None, frames=None):
    """The text's own lines placed one per manuscript line slot (label-like slots skipped): each printed line starts
    where the manuscript line starts, runs its own length at the slot line's letter size (the same rule as every other
    control), keeps the manuscript line's drawing gaps and follows the recorded line's drift. Returns (lines as placed,
    geometry, start)."""
    frames = frames or line_frames(app, ms)
    skip = [label_like_slot(L) for L in ms.lines]
    need = len(ms.lines) - sum(skip)
    if start is None:
        start = int(rng.integers(0, len(lines) - need))
    chosen, geometry = fill_slots(ms, frames, lines[start:start + need], 'lines', skip=skip)
    return chosen, geometry, start


# ---- Markov chains
class Bigram:
    """Interpolated word-bigram sampler: P(w | prev) = (c(prev, w) + a p1(w)) / (c(prev) + a)."""

    def __init__(self, words, rng, a=1.0):
        self.rng = rng
        self.a = a
        self.uni = Counter(words)
        self.vocab = np.array(list(self.uni), dtype=object)
        self.p1 = np.array([self.uni[w] for w in self.vocab], dtype=float)
        self.p1 /= self.p1.sum()
        self.index = {w: i for i, w in enumerate(self.vocab)}
        self.big = defaultdict(Counter)
        for x, y in zip(words[:-1], words[1:]):
            self.big[x][y] += 1
        self.cache = {}
        self.prev = None

    def dist(self, prev):
        if prev not in self.cache:
            c = self.big.get(prev)
            if not c:
                self.cache[prev] = self.p1
            else:
                p = self.a * self.p1.copy()
                for w, k in c.items():
                    p[self.index[w]] += k
                self.cache[prev] = p / p.sum()
        return self.cache[prev]

    def draw(self, n):
        out = []
        for _ in range(n):
            w = self.vocab[self.rng.choice(len(self.vocab), p=self.dist(self.prev))]
            out.append(w)
            self.prev = w
        return out


def currier_of(ms) -> Callable[[dict], str]:
    """Currier language of a line's page; pages without a label take their Golf side."""
    a_side = {'1a', '1b', '1.5a', '2a'}

    def f(L):
        c = ms.pages[L['page']]['currier']
        return c if c in ('A', 'B') else ('A' if L['group'] in a_side else 'B')
    return f


def section_of_line(ms) -> Callable[[dict], str]:
    return lambda L: ms.pages[L['page']]['section']


MARKOV_KINDS = ('whole', 'currier', 'section')


def markov_text(ms, kind='whole', rng=None, source_lines=None, fill='chars') -> List[List[str]]:
    """A word-bigram text in the manuscript's lines. kind: 'whole' (one chain), 'currier' (one chain for the Currier A
    pages and one for the B pages), 'section' (one chain per section letter). fill='chars' (the default) fills each line
    to the manuscript line's character budget, the chain running on across lines (a word that does not fit opens the
    next line of its chain), ready for typesetting by character position; fill='words' draws the manuscript line's word
    count instead, which only the one-word-per-box diagnostic wants. `source_lines` trains the chains on another
    line-aligned text instead of the manuscript."""
    rng = rng or np.random.default_rng(20261027)
    src = source_lines or [L['words'] for L in ms.lines]
    if kind == 'whole':
        class_of = lambda L: 'all'                                   # noqa: E731
    elif kind in ('currier', 'section'):
        class_of = currier_of(ms) if kind == 'currier' else section_of_line(ms)
    else:
        raise ValueError('kind must be one of %s' % (MARKOV_KINDS,))
    classes = {}
    for L, ws in zip(ms.lines, src):
        classes.setdefault(class_of(L), []).extend(ws)
    models = {c: Bigram(ws, rng) for c, ws in classes.items()}
    if fill == 'words':
        return [models[class_of(L)].draw(len(L['words'])) for L in ms.lines]
    if fill != 'chars':
        raise ValueError("fill must be 'chars' or 'words'")
    pending: Dict[str, Optional[str]] = {c: None for c in models}
    out = []
    for L in ms.lines:
        c = class_of(L)
        model = models[c]
        line, used = [], 0
        w = pending[c] if pending[c] is not None else model.draw(1)[0]
        while not line or used + 1 + len(w) <= L['chars']:
            used += len(w) + (1 if line else 0)
            line.append(w)
            w = model.draw(1)[0]
        pending[c] = w
        out.append(line)
    return out


# ---- one place to build any control with its geometry
def clean_recorded(app, ms) -> list:
    """The recorded rectangles with the oversized ones removed: the geometry the one-word-per-box diagnostics reuse."""
    from .geometry import oversized_flags
    flags = oversized_flags(app, ms)
    return [None if flags[i] else g for i, g in enumerate(app['geometry'])]


DIAGNOSTIC_KINDS = ('markov_box', 'prose_box')
KINDS = ('stream', 'markov', 'prose', 'prose_native') + DIAGNOSTIC_KINDS


def build_control(ms, app, kind, name=None, seed=None, frames=None, start=None, check=True):
    """(line_words, geometry, component mode, info) for ('stream', key[, seed index]), ('markov', whole|currier|section),
    ('prose', text) and ('prose_native', text): every one typeset into the line frames by character position
    (geometry_kind 'synthetic'); info['typesetting'] holds the width check, which must pass unless check=False. The
    diagnostics ('markov_box', chain) and ('prose_box', text) reuse the manuscript's recorded rectangles one word per box
    (geometry_kind 'recorded'), warn, and carry info['caveat']: they are not controls (PITFALLS 4). 'prose_line' is the
    former name of 'prose'. A prose text's passage start travels in info so that the bundle records it."""
    frames = frames or line_frames(app, ms)
    rng = np.random.default_rng(seed if seed is not None else 20261027)
    if kind == 'prose_line':
        kind = 'prose'
    geometry = None
    if kind == 'stream':
        label, srcs = STREAMS[name]
        src = srcs[seed] if isinstance(seed, int) and seed < len(srcs) else srcs[0]
        lines = read_stream(src)
        info = dict(geometry_kind='synthetic', source=str(src), label=label, layout='line-aligned, typeset')
        components = 'zattera'
    elif kind == 'markov':
        lines = markov_text(ms, name or 'whole', rng)
        info = dict(geometry_kind='synthetic', chain=name or 'whole', seed=seed, layout='filled to the character budget, typeset')
        components = 'zattera'
    elif kind == 'prose':
        lines, start = fill_by_chars(ms, ref_words(name), rng, start=start)
        info = dict(geometry_kind='synthetic', text=name, start=start, layout='filled to the character budget, typeset')
        components = 'letters'
    elif kind == 'prose_native':
        lines, geometry, start = native_layout(ms, app, native_lines(name), rng, start=start, frames=frames)
        info = dict(geometry_kind='synthetic', text=name, start=start, layout='own printed lines, typeset')
        components = 'letters'
    elif kind in DIAGNOSTIC_KINDS:
        caveat = ('%s puts each word into the recorded rectangle of the manuscript word it replaces: the box widths belong to other '
                  'words, and every distance-weighted pool reads those widths. A diagnostic of that error, not a control (PITFALLS 4).' % kind)
        warnings.warn(caveat, stacklevel=2)
        if kind == 'markov_box':
            lines = markov_text(ms, name or 'whole', rng, fill='words')
            info = dict(geometry_kind='recorded', chain=name or 'whole', seed=seed, layout='one word per recorded box', caveat=caveat)
            components = 'zattera'
        else:
            lines, start = laid_in(ms, ref_words(name), rng, start=start)
            info = dict(geometry_kind='recorded', text=name, start=start, layout='one word per recorded box', caveat=caveat)
            components = 'letters'
        return lines, clean_recorded(app, ms), components, info
    else:
        raise ValueError('unknown control kind %r; one of %s' % (kind, ', '.join(KINDS)))
    if geometry is None:
        geometry = synthetic_geometry(lines, frames, ms)
    from .shuffles import check_typesetting
    report = check_typesetting(ms, frames, lines, geometry, raise_on_fail=check)
    info['typesetting'] = dict(ok=report['ok'], off_1p5=report['width']['off_1p5'], median_abslog=report['width']['median_abslog'],
                               boxed=report['width']['boxed'], no_box=report['no_box'], overlaps=report['overlaps'])
    return lines, geometry, components, info
