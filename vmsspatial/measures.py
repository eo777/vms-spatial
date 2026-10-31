"""Per-pool and per-stream measures.

Pool measures (``measure``; ``js/sources.js`` ``measure``, ported): with each pooled word weighted by its pool weight,
    worddiv      1 - sum p(spelling)^2, the chance that two weighted draws differ in spelling
    h1           entropy (bits) of the glyph units
    h2           conditional entropy of the next unit given the current one: H(pairs) - H(left units)
    components   2^H(pairs): the effective number of within-word unit-pair types ("component diversity")
    js           Jensen-Shannon distance between the pool's pair distribution and the whole stream's
    n, ess       pool size and effective sample size 1/sum p(token)^2; pair_words, pair_ess the same for the words that
                 contribute pairs; distinct spellings; available (candidates before the cap)
Each word contributes its normalized unit and pair histograms, so long words do not weigh more. h1 needs n >= 5 and
ess >= 3; the pair measures need pair_words >= 5 and pair_ess >= 3 and a complete window; otherwise NaN.

CAVEATS FROM THE 28 OCTOBER 2026 REVIEWS. (1) worddiv carries a weighting term (1 - 1/ESS): with distance weights it is
not an order-free measure of lexical variety and is the weakest and most geometry-dependent of the three; components and
H2 carry the published results. (2) Every pool measure depends on the pool's size (small pools at the top of a page or
paragraph are low in diversity whatever the text) and, with the study selector, on the target's own length (see
selector.py): read them inside pool-size tertiles and exact length classes (stats.standard_contrasts), never raw alone.
(3) The measures depend on the geometry kind: the same prose scores differently on recorded and on synthetic
length-proportional rectangles; report the kind with every number (SpatialContext.describe()).

Stream measures: MATTR (moving-average type-token ratio) and its exact shuffled-bag expectation, the rolling distinct
count with repeat flags, bifolium means over complete windows, and the fresh-word indicator.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

from .selector import Pool, PoolSpec, SpatialContext, STUDY_SELECTOR

MEASURE_KEYS = ('components', 'h1', 'h2', 'worddiv', 'js', 'n', 'ess', 'pair_words', 'pair_ess', 'available', 'distinct')


def entropy(v: np.ndarray) -> float:
    total = float(v.sum())
    if not total:
        return float('nan')
    p = v[v > 0] / total
    return float(-(p * np.log2(p)).sum())


def js_distance(a: np.ndarray, b: np.ndarray) -> float:
    sa, sb = float(a.sum()), float(b.sum())
    if not sa or not sb:
        return float('nan')
    p, q = a / sa, b / sb
    m = (p + q) / 2
    with np.errstate(divide='ignore', invalid='ignore'):
        d = np.where(p > 0, p * np.log2(p / m) / 2, 0.0).sum() + np.where(q > 0, q * np.log2(q / m) / 2, 0.0).sum()
    return float(np.sqrt(max(0.0, d)))


class Features:
    """Unit and pair features of every word of a bundle, in compressed arrays for fast pool measures."""

    def __init__(self, bundle: dict):
        comps: Dict[str, List[str]] = bundle['components']
        words = bundle['words']
        self.unit_ids: Dict[str, int] = {}
        self.pair_ids: Dict[tuple, int] = {}
        self.unit_names: List[str] = []
        self.pair_names: List[str] = []
        pair_left: List[int] = []
        word_index = {}
        mono_ptr, mono_ids, mono_p = [0], [], []
        pair_ptr, pair_ids, pair_p = [0], [], []
        for w, units in comps.items():
            ids = []
            for u in units:
                if u not in self.unit_ids:
                    self.unit_ids[u] = len(self.unit_ids)
                    self.unit_names.append(u)
                ids.append(self.unit_ids[u])
            mono = Counter(ids)
            for k, c in mono.items():
                mono_ids.append(k)
                mono_p.append(c / len(ids))
            mono_ptr.append(len(mono_ids))
            pairs = Counter()
            for a, b in zip(ids, ids[1:]):
                key = (a, b)
                if key not in self.pair_ids:
                    self.pair_ids[key] = len(self.pair_ids)
                    self.pair_names.append(units[ids.index(a)] + '·' + units[ids.index(b)] if False else '%s·%s' % (self.unit_names[a], self.unit_names[b]))
                    pair_left.append(a)
                pairs[self.pair_ids[key]] += 1
            for k, c in pairs.items():
                pair_ids.append(k)
                pair_p.append(c / (len(ids) - 1))
            pair_ptr.append(len(pair_ids))
            word_index[w] = len(word_index)
        self.n_units, self.n_pairs = len(self.unit_names), len(self.pair_names)
        self.pair_left = np.array(pair_left, dtype=np.int64)
        self.mono_ptr, self.mono_ids, self.mono_p = np.array(mono_ptr), np.array(mono_ids, dtype=np.int64), np.array(mono_p)
        self.pair_ptr, self.pair_ids_arr, self.pair_p = np.array(pair_ptr), np.array(pair_ids, dtype=np.int64), np.array(pair_p)
        self.word_of_token = np.array([word_index[w] for w in words], dtype=np.int64)
        self.has_pairs = (self.pair_ptr[1:] - self.pair_ptr[:-1]) > 0
        self.baseline = np.zeros(self.n_pairs)
        for wid in self.word_of_token:
            s, e = self.pair_ptr[wid], self.pair_ptr[wid + 1]
            np.add.at(self.baseline, self.pair_ids_arr[s:e], self.pair_p[s:e])

    def _gather(self, ptr, wid):
        starts, lens = ptr[wid], ptr[wid + 1] - ptr[wid]
        total = int(lens.sum())
        if not total:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        rep = np.repeat(np.arange(len(wid)), lens)
        pos = np.repeat(starts - np.cumsum(lens) + lens, lens) + np.arange(total)
        return pos, rep


def measure(features: Features, pool: Pool, words: Optional[List[str]] = None, detail: bool = False) -> dict:
    """The pool measures of one pool (see the module docstring)."""
    idx, w = np.asarray(pool.indices, dtype=np.int64), np.asarray(pool.weights, float)
    n = len(idx)
    out = dict(n=n, ess=0.0, pair_words=0, pair_ess=0.0, available=pool.available, worddiv=float('nan'), h1=float('nan'),
               h2=float('nan'), components=float('nan'), js=float('nan'), distinct=0)
    if not n:
        return out
    wid = features.word_of_token[idx]
    mass = float(w.sum())
    squared = float((w * w).sum())
    uniq, inv = np.unique(wid, return_inverse=True)
    type_mass = np.bincount(inv, weights=w)
    collision = float(((type_mass / mass) ** 2).sum())
    pos, rep = features._gather(features.mono_ptr, wid)
    mono = np.bincount(features.mono_ids[pos], weights=w[rep] * features.mono_p[pos], minlength=features.n_units)
    ppos, prep = features._gather(features.pair_ptr, wid)
    pairs = np.bincount(features.pair_ids_arr[ppos], weights=w[prep] * features.pair_p[ppos], minlength=features.n_pairs)
    hp = features.has_pairs[wid]
    pair_words = int(hp.sum())
    pair_mass = float(w[hp].sum())
    pair_squared = float((w[hp] ** 2).sum())
    lefts = np.bincount(features.pair_left, weights=pairs, minlength=features.n_units) if features.n_pairs else np.zeros(features.n_units)
    ess = mass * mass / squared if squared else 0.0
    pair_ess = pair_mass * pair_mass / pair_squared if pair_squared else 0.0
    full = pool.full is not False
    mono_ok = full and n >= 5 and ess >= 3
    pair_ok = full and pair_words >= 5 and pair_ess >= 3
    pair_h = entropy(pairs)
    out.update(ess=ess, pair_words=pair_words, pair_ess=pair_ess, worddiv=max(0.0, 1 - collision), distinct=int(len(uniq)),
               h1=entropy(mono) if mono_ok else float('nan'),
               h2=max(0.0, pair_h - entropy(lefts)) if pair_ok else float('nan'),
               components=2 ** pair_h if pair_ok else float('nan'),
               js=js_distance(pairs, features.baseline) if pair_ok else float('nan'))
    if detail:
        def top(values, names, k=8):
            total = values.sum()
            order = np.argsort(-values, kind='stable')
            return [dict(name=names[j], p=float(values[j] / total)) for j in order[:k] if values[j] > 0]
        out['top_units'] = top(mono, features.unit_names)
        out['top_pairs'] = top(pairs, features.pair_names)
        if words is not None:
            order = np.argsort(-type_mass, kind='stable')
            out['types'] = [dict(word=words[idx[np.flatnonzero(inv == j)[0]]], p=float(type_mass[j] / mass)) for j in order]
    return out


def score(ctx: SpatialContext, spec: PoolSpec = STUDY_SELECTOR, features: Optional[Features] = None, indices=None,
          progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, np.ndarray]:
    """Per-token pool measures over the whole stream (or `indices`): arrays keyed by MEASURE_KEYS plus `missing`."""
    features = features or Features(ctx.bundle)
    idx = np.arange(ctx.n) if indices is None else np.asarray(indices)
    out = {k: np.full(ctx.n, np.nan) for k in MEASURE_KEYS}
    out['missing'] = np.ones(ctx.n, bool)
    for k, i in enumerate(idx):
        if progress and k % 2000 == 0:
            progress(k, len(idx))
        p = ctx.pool(int(i), spec)
        out['missing'][i] = p.missing_target
        m = measure(features, p)
        for key in MEASURE_KEYS:
            out[key][i] = m[key]
    for key in ('n', 'pair_words', 'available', 'distinct'):
        out[key] = np.nan_to_num(out[key]).astype(np.int64)
    return out


def score_window(ctx: SpatialContext, width: int = 99, direction: str = 'backward', features: Optional[Features] = None,
                 exclude_target: bool = True) -> Dict[str, np.ndarray]:
    """Reading-order neighbourhood measures: the `width` tokens before (or after) each token, excluding it."""
    features = features or Features(ctx.bundle)
    out = {k: np.full(ctx.n, np.nan) for k in MEASURE_KEYS}
    shift = (-1 if direction == 'backward' else 1) if exclude_target else 0
    for i in range(ctx.n):
        m = measure(features, ctx.window_pool(i + shift, width, direction))
        for key in MEASURE_KEYS:
            out[key][i] = m[key]
    return out


def score_many(ctx: SpatialContext, specs: Iterable[PoolSpec], features: Optional[Features] = None) -> Dict[str, Dict[str, np.ndarray]]:
    features = features or Features(ctx.bundle)
    return {s.label(): score(ctx, s, features) for s in specs}


# ---- stream measures
def mattr(words, w=100) -> float:
    n = len(words)
    if n == 0:
        return float('nan')
    if n <= w:
        return len(set(words)) / n
    c = Counter(words[:w])
    total = len(c)
    for i in range(w, n):
        old = words[i - w]
        c[old] -= 1
        if not c[old]:
            del c[old]
        c[words[i]] += 1
        total += len(c)
    return total / (w * (n - w + 1))


def bag_mattr(words, w=100) -> float:
    """Exact expected MATTR_w of a uniform random permutation of the bag (hypergeometric)."""
    c = np.array(list(Counter(words).values()), dtype=float)
    n = len(words)
    w = min(n, w)
    if n == 0:
        return float('nan')
    sure = n - c < w
    remaining = c[~sure]
    logs = np.log1p(-remaining[:, None] / (n - np.arange(w))).sum(axis=1)
    return float((sure.sum() + (-np.expm1(logs)).sum()) / w)


def iid_mattr(probs, w=100) -> float:
    p = np.asarray(list(probs), dtype=float)
    return float((1 - (1 - p) ** w).sum() / w)


def trailing_distinct(words, w=100) -> np.ndarray:
    """D_w at every position: distinct among tokens [i-w+1, i] / w; NaN before w tokens exist."""
    counts = Counter()
    out = np.full(len(words), np.nan)
    for i, x in enumerate(words):
        counts[x] += 1
        if i >= w:
            old = words[i - w]
            counts[old] -= 1
            if not counts[old]:
                del counts[old]
        if i >= w - 1:
            out[i] = len(counts) / w
    return out


def fresh_indicator(words, w=100) -> np.ndarray:
    """1 if the word did not occur among the previous w tokens."""
    last = {}
    out = np.zeros(len(words), dtype=np.int8)
    for i, x in enumerate(words):
        j = last.get(x)
        out[i] = 1 if (j is None or i - j > w) else 0
        last[x] = i
    return out


def window_bounds(pos, width, direction, length):
    before = 0 if direction == 'forward' else ((width - 1) // 2 if direction == 'centered' else width - 1)
    first, last = pos - before, pos - before + width
    return max(0, first), min(length, last), first >= 0 and last <= length


def rolling_series(words, width=100, direction='backward'):
    """(scores, repeated): the distinct share of every complete window and whether the word recurs in its own window
    (``js/heatmap_math.js`` ``series``)."""
    n = len(words)
    scores = np.full(n, np.nan)
    repeated = np.zeros(n, dtype=np.int8)
    counts = Counter()
    start = end = 0
    for i in range(n):
        s, e, full = window_bounds(i, width, direction, n)
        while end < e:
            counts[words[end]] += 1
            end += 1
        while start < s:
            counts[words[start]] -= 1
            if not counts[words[start]]:
                del counts[words[start]]
            start += 1
        if full:
            scores[i] = len(counts) / width
        repeated[i] = 1 if counts[words[i]] > 1 else 0
    return scores, repeated


def mean_within(scores, ranges, width=100, direction='backward'):
    """Mean score over the windows wholly inside one of the token `ranges` [(start, end), ...] (a sheet's ranges from
    ``Manuscript.bifolium_ranges``; the row means of the heatmap)."""
    n = len(scores)
    vals = []
    for start, end in ranges:
        for i in range(start, end):
            s, e, full = window_bounds(i, width, direction, n)
            if full and s >= start and e <= end and np.isfinite(scores[i]):
                vals.append(scores[i])
    return float(np.mean(vals)) if vals else None


def group_table(ms, line_words, groups=None, w=100) -> dict:
    """MATTR_w, bag expectation and clustering gap by Golf group and by bifolium, with the late steps split into bag and
    clustering parts (``layout_controls.group_table``). A group's or a sheet's words are gathered by label, wherever they
    fall in the stream, so the table holds for any order that keeps a sheet's pages in their order."""
    from collections import defaultdict
    groups = groups or [g for g in ['1a', '1b', '1.5a', '2a', '5a', '6', '3b', '3a', '3c', '4c', '4a'] if any(n['group'] == g for n in ms.nodes)]
    words_by, by_node = defaultdict(list), defaultdict(list)
    for L, ws in zip(ms.lines, line_words):
        words_by[L['group']] += list(ws)
        by_node[L['node']] += list(ws)
    out = {}
    for g in groups:
        ws = words_by[g]
        m, b = mattr(ws, w), bag_mattr(ws, w)
        out[g] = dict(tokens=len(ws), mattr=m, bag=b, gap=b - m)
    steps = {}
    for a, b in (('3c', '4c'), ('4c', '4a'), ('3c', '4a')):
        if a in out and b in out:
            steps['%s->%s' % (a, b)] = dict(actual=out[b]['mattr'] - out[a]['mattr'], bag=out[b]['bag'] - out[a]['bag'], clustering=out[a]['gap'] - out[b]['gap'])
    nodes = {}
    for n in ms.nodes:
        ws = by_node[n['id']]
        m, b = mattr(ws, w), bag_mattr(ws, w)
        nodes[n['id']] = dict(group=n['group'], tokens=len(ws), mattr=m, bag=b, gap=b - m)
    return dict(window=w, groups=out, steps=steps, nodes=nodes)
