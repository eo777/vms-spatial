"""Word positions for the Rosettes foldout (ZL page fRos), which the Voynichese Project did not record.

`build(image_path, ...)` reads the page's 160 loci from the ZL transliteration (the lattice parser keeps the locus
types and the transcriber's comments: Petersen's circle:label numbers, the clock position where each circular text
starts, 'Spiral', the roman-numeral groups), finds candidate word regions on the Beinecke image and links the
tokens to them (see vmsspatial.segment for the method), and returns a supplement record: one entry per token with
its box in full-resolution pixels and on the display image, a method and a confidence. Nothing here reads glyphs.

    python scripts/rosettes_geometry.py --image data/images/beinecke/fRos_1006231.jpg --overlay review.jpg
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import paths
from . import segment as S
from .units import zattera

COMMENT_RE = re.compile(r'<!([^>]*)>')
CLOCK_RE = re.compile(r'^\d{1,2}:\d{2}$')
PETERSEN_RE = re.compile(r'^(\d+):(\d+)$')
ROMAN_RE = re.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X)$')


def load_layout(path=None) -> dict:
    p = Path(path) if path else paths.resource('rosettes_layout.json')
    return json.loads(p.read_text(encoding='utf-8'))


def glyph_count(text: str) -> int:
    t = text.replace('?', 'x')
    try:
        return max(1, len(zattera(t)))
    except Exception:
        return max(1, len(t))


def read_loci(page: str = 'fRos', raw=None) -> List[dict]:
    """The page's loci from the ZL lattice, in file order: {num, type, locator, comments, tokens:[{id, text, glyphs}]}."""
    from .audit._zl.source_lattice import SourceLattice
    lat = SourceLattice(Path(raw) if raw else paths.resolve('raw/ZL_ivtff_raw.txt'))
    out = []
    for lt in lat.stream():
        L = lt.locus
        if L.page != page:
            continue
        comments = COMMENT_RE.findall(L.raw_line)
        toks = [dict(id=t.token_id, text=t.text, glyphs=glyph_count(t.text), index=t.index_in_locus) for t in lt.tokens]
        out.append(dict(num=int(L.num), type=L.locus_type, locator=L.locator, comments=comments, tokens=toks, raw=L.raw_line))
    return out


def classify(loci: Sequence[dict], layout: dict) -> Dict[str, list]:
    """Sort the loci into rings (circular text), Petersen label groups by circle, roman-numeral groups and the
    clock labels, from the comments."""
    rings, petersen, roman, clock, other = [], {}, {}, [], []
    current_roman = None
    for L in loci:
        key = str(L['num'])
        if L['type'] in ('Cc', 'Ca'):
            rings.append(L)
            continue
        pet = [m for c in L['comments'] for m in [PETERSEN_RE.match(c)] if m]
        rom = [m for c in L['comments'] for m in [ROMAN_RE.match(c)] if m]
        if pet:
            circle, k = pet[0].group(1), int(pet[0].group(2))
            petersen.setdefault(circle, []).append(dict(L, k=k))
            current_roman = None
        elif rom:
            current_roman = rom[0].group(1)
            roman.setdefault(current_roman, []).append(L)
        elif key in layout.get('clock_labels', {}):
            clock.append(dict(L, side=layout['clock_labels'][key]))
            current_roman = None
        elif current_roman and L['locator'] in ('+', '*', '/', '='):
            roman[current_roman].append(L)
        else:
            other.append(L)
    for circle in petersen:
        petersen[circle].sort(key=lambda L: L['k'])
    return dict(rings=rings, petersen=petersen, roman=roman, clock=clock, other=other)


# ---------------------------------------------------------------- rings
def ring_for(locus: dict, spec: dict, layout: dict, mask: np.ndarray) -> Tuple[S.Ring, dict]:
    """The Ring geometry of a circular locus: its rosette (or small circle), band and start angle; an ambiguous
    rosette pair is resolved by the ink length of each band against the locus's glyph count."""
    start = 0.0
    for c in locus['comments']:
        if CLOCK_RE.match(c):
            start = S.clock_to_deg(c)
    clockwise = locus['type'] != 'Ca'
    glyphs = sum(t['glyphs'] for t in locus['tokens'])
    if 'circle' in spec:
        c = layout['circles'][spec['circle']]
        return S.Ring(c['cx'], c['cy'], c['band'][0], c['band'][1], start, clockwise, name=str(locus['num'])), dict(circle=spec['circle'])
    choices = spec['rosette'].split('|')
    best = None
    for r in choices:
        ro = layout['rosettes'][r]
        ring = S.Ring(ro['cx'], ro['cy'], ro['band'][0], ro['band'][1], start, clockwise, name=str(locus['num']))
        if len(choices) == 1:
            return ring, dict(rosette=r)
        mstrip, _ = S.unwrap(mask, ring)
        runs = S.ink_runs((mstrip > 0).astype(np.uint8), None, min_gap=9)
        ink = sum(b - a for a, b in runs)
        per_glyph = ink / max(1, glyphs)
        # a plausible per-glyph width lies between 18 and 45 px at this resolution
        score = abs(math.log(max(1e-6, per_glyph) / 30.0))
        if best is None or score < best[0]:
            best = (score, ring, r, per_glyph)
    return best[1], dict(rosette=best[2], per_glyph=round(best[3], 1), resolved_from=choices)


def spiral_ring(locus: dict, spec: dict, layout: dict) -> List[S.Ring]:
    """Both windings of a spiral (outer to inner and inner to outer) as Rings with changing radius."""
    ro = layout['rosettes'][spec['rosette']]
    sp = spec['spiral']
    h = sp.get('height', 70)
    out = []
    for direction in ('inward', 'outward'):
        r_a, r_b = (sp['r_outer'], sp['r_inner']) if direction == 'inward' else (sp['r_inner'], sp['r_outer'])
        out.append(S.Ring(ro['cx'], ro['cy'], r_a - h / 2, r_a + h / 2, 0.0, locus['type'] != 'Ca', name='%s-%s' % (locus['num'], direction),
                          r0_end=r_b - h / 2, r1_end=r_b + h / 2, turns=sp.get('turns', 1.5)))
    return out


def segment_ring(mask: np.ndarray, ring: S.Ring, tokens: Sequence[dict]) -> dict:
    mstrip, to_image = S.unwrap(mask, ring)
    mstrip = (mstrip > 0).astype(np.uint8)
    rows = (0, mstrip.shape[0])
    res = S.strip_words(mstrip, [t['glyphs'] for t in tokens], rows)
    boxes = S.strip_boxes_to_image(res['segments'], rows, to_image) if res['segments'] else [None] * len(tokens)
    return dict(boxes=boxes, confidence=res['confidence'], error=res.get('error'), runs=res.get('runs'), min_gap=res.get('min_gap'))


# ---------------------------------------------------------------- labels
def territory(candidates: Sequence[dict], layout: dict) -> Dict[str, List[dict]]:
    """Each candidate goes to the rosette whose centre is nearest (relative to that rosette's ring radius)."""
    out: Dict[str, List[dict]] = {k: [] for k in layout['rosettes']}
    for c in candidates:
        b = c['box']
        x, y = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        best = min(layout['rosettes'].items(), key=lambda kv: math.hypot(x - kv[1]['cx'], y - kv[1]['cy']) / kv[1]['band'][1])
        out[best[0]].append(c)
    return out


def overlaps(box, others: Sequence[Sequence[int]], frac: float = 0.4) -> bool:
    x0, y0, x1, y1 = box
    area = max(1, (x1 - x0) * (y1 - y0))
    for o in others:
        if not o:
            continue
        iw, ih = min(x1, o[2]) - max(x0, o[0]), min(y1, o[3]) - max(y0, o[1])
        if iw > 0 and ih > 0 and iw * ih >= frac * area:
            return True
    return False


def label_items(loci: Sequence[dict]) -> List[dict]:
    """Tokens of a label group in order: (Petersen k, then token order); a locus's tokens stay consecutive."""
    items = []
    for L in loci:
        for t in L['tokens']:
            items.append(dict(locus=L['num'], token=t['id'], text=t['text'], glyphs=t['glyphs']))
    return items


def assign_group(items: Sequence[dict], candidates: Sequence[dict], per_glyph: float, cx: float, cy: float, hypotheses=('cw', 'ccw', 'reading')) -> dict:
    if not items:
        return dict(boxes=[], confidence=0.0, hypothesis=None)
    if not candidates:
        return dict(boxes=[None] * len(items), confidence=0.0, hypothesis=None, cost=float('inf'), matched=0)
    return S.best_assignment(items, candidates, per_glyph, cx, cy, hypotheses=hypotheses)


# ---------------------------------------------------------------- the whole page
def build(image_path, layout: Optional[dict] = None, candidates: Optional[Sequence[dict]] = None, candidate_cache=None, log=print) -> dict:
    layout = layout or load_layout()
    loci = read_loci(layout.get('page', 'fRos'))
    groups = classify(loci, layout)
    gray = S.load_gray(image_path)
    H, W = gray.shape
    mask = S.ink_mask(gray)
    if candidates is None:
        candidates = S.craft_candidates(image_path, cache=candidate_cache, log=log)
    f = layout.get('candidate_filter', {})
    cands = [c for c in S.dedupe_boxes(candidates)
             if f.get('min_height', 0) <= c['box'][3] - c['box'][1] <= f.get('max_height', 1e9) and c['box'][2] - c['box'][0] >= f.get('min_width', 0)]
    records: Dict[str, dict] = {}
    per_glyph_est = []

    def put(token, box, method, confidence, **extra):
        records[token['id'] if isinstance(token, dict) else token] = dict(box=[int(v) for v in box] if box else None, method=method,
                                                                          confidence=round(float(confidence), 3), **extra)

    # rings; loci whose layout entry offers the same pair of rosettes are resolved jointly (one each)
    ring_boxes = []
    pair_members = {}
    for L in groups['rings']:
        spec = layout['rings'].get(str(L['num']))
        if spec and 'rosette' in spec and '|' in spec['rosette']:
            pair_members.setdefault(frozenset(spec['rosette'].split('|')), []).append(L)
    forced = {}
    for pair, members in pair_members.items():
        if len(members) == 2 and len(pair) == 2:
            a, b = members
            ra, rb = sorted(pair)
            def fit(L, r):
                ro = layout['rosettes'][r]
                ring = S.Ring(ro['cx'], ro['cy'], ro['band'][0], ro['band'][1], 0.0, True)
                mstrip, _ = S.unwrap(mask, ring)
                ink = sum(e - s_ for s_, e in S.ink_runs((mstrip > 0).astype(np.uint8), None, min_gap=9))
                return abs(math.log(max(1e-6, ink / max(1, sum(t['glyphs'] for t in L['tokens']))) / 30.0))
            if fit(a, ra) + fit(b, rb) <= fit(a, rb) + fit(b, ra):
                forced[a['num']], forced[b['num']] = ra, rb
            else:
                forced[a['num']], forced[b['num']] = rb, ra
            log('rings %d and %d share rosettes %s: assigned %s and %s by ink length' % (a['num'], b['num'], sorted(pair), forced[a['num']], forced[b['num']]))
    for L in groups['rings']:
        spec = layout['rings'].get(str(L['num']))
        if spec and L['num'] in forced:
            spec = dict(spec, rosette=forced[L['num']])
        if not spec:
            log('ring locus %d has no layout entry; skipped' % L['num'])
            for t in L['tokens']:
                put(t, None, 'ring-unplaced', 0.0, locus=L['num'])
            continue
        if 'spiral' in spec:
            best = None
            for ring in spiral_ring(L, spec, layout):
                res = segment_ring(mask, ring, L['tokens'])
                if best is None or res['confidence'] > best[0]['confidence']:
                    best = (res, ring)
            res, ring = best
            info = dict(rosette=spec['rosette'], spiral=ring.name.split('-')[-1])
            method = 'spiral'
        else:
            ring, info = ring_for(L, spec, layout, mask)
            res = segment_ring(mask, ring, L['tokens'])
            method = 'ring'
        conf = res['confidence'] * (0.7 if layout['rosettes'].get(info.get('rosette', ''), {}).get('irregular') else 1.0)
        log('locus %d (%s, %d words): %s %s, fit error %.2f, confidence %.2f' % (L['num'], L['type'], len(L['tokens']), method, info, res['error'] or 0, conf))
        for t, b in zip(L['tokens'], res['boxes']):
            put(t, b, method, conf, locus=L['num'], **info)
            if b:
                ring_boxes.append(b)
        if res['boxes'] and res['boxes'][0]:
            widths = [b[2] - b[0] for b in res['boxes'] if b]
            per_glyph_est.append(sum(widths) / max(1, sum(t['glyphs'] for t in L['tokens'])))
    per_glyph = float(np.median(per_glyph_est)) if per_glyph_est else 30.0
    # labels: candidates not on a ring, by rosette territory
    free = [c for c in cands if not overlaps(c['box'], ring_boxes)]
    terr = territory(free, layout)
    used: List[Sequence[int]] = []
    for circle, loci_c in groups['petersen'].items():
        ro = layout['rosettes'].get(circle)
        if not ro:
            continue
        pool = list(terr.get(circle, []))
        # label columns first: a run of loci joined by the '+' locator (consecutive lines of one label block) is matched
        # as a whole to the cluster of stacked candidates that fits it best, so a block cannot be scattered
        blocks, run = [], []
        for L in sorted(loci_c, key=lambda L: L['num']):
            if run and L['locator'] in ('+', '*', '/', '=') and L['num'] == run[-1]['num'] + 1:
                run.append(L)
            else:
                if len(run) >= 3:
                    blocks.append(run)
                run = [L]
        if len(run) >= 3:
            blocks.append(run)
        block_tokens = set()
        for block in blocks:
            items = label_items(block)
            best = None
            for cl in S.clusters(pool):
                if len(cl) < len(block) - 1:
                    continue
                assign, cost = S.assign_sequence(items, S.reading_order(cl), per_glyph)
                matched = sum(1 for a in assign if a is not None)
                score = cost / max(1, len(items))
                if matched >= max(2, len(items) // 2) and (best is None or score < best[0]):
                    best = (score, assign, S.reading_order(cl), matched)
            if best is None or best[0] > 1.6:
                continue
            score, assign, ordered, matched = best
            conf = matched / len(items) / (1.0 + score)
            log('circle %s: label block %d-%d (%d tokens) -> a %d-candidate cluster, matched %d, confidence %.2f'
                % (circle, block[0]['num'], block[-1]['num'], len(items), len(ordered), matched, conf))
            for it, a in zip(items, assign):
                b = ordered[a]['box'] if a is not None else None
                put(it['token'], b, 'label-block', conf, locus=it['locus'], rosette=circle, hypothesis='block')
                block_tokens.add(it['token'])
                if b:
                    used.append(b)
            pool = [c for c in pool if not any(c is ordered[a] for a in assign if a is not None)]
        items = [it for it in label_items(loci_c) if it['token'] not in block_tokens]
        res = assign_group(items, pool, per_glyph, ro['cx'], ro['cy'])
        log('circle %s: %d label tokens, %d candidates in territory, hypothesis %s (start %s), matched %d, confidence %.2f'
            % (circle, len(items), len(pool), res.get('hypothesis'), res.get('start'), res.get('matched', 0), res.get('confidence', 0)))
        for it, b in zip(items, res['boxes']):
            put(it['token'], b, 'label', res.get('confidence', 0), locus=it['locus'], rosette=circle, hypothesis=res.get('hypothesis'))
            if b:
                used.append(b)
    # clock labels: nearest free candidate on the given side of the small circle
    clock = layout['circles'].get('clock')
    for L in groups['clock']:
        side = L['side']
        pool = [c for c in free if not overlaps(c['box'], used) and abs((c['box'][1] + c['box'][3]) / 2 - clock['cy']) < 3 * clock['band'][1]
                and ((c['box'][2] < clock['cx'] - clock['band'][0]) if side == 'left' else (c['box'][0] > clock['cx'] + clock['band'][0]))
                and abs((c['box'][0] + c['box'][2]) / 2 - clock['cx']) < 4 * clock['band'][1]]
        pool.sort(key=lambda c: abs((c['box'][0] + c['box'][2]) / 2 - clock['cx']))
        for t in L['tokens']:
            b = pool.pop(0)['box'] if pool else None
            put(t, b, 'clock-label', 0.5 if b else 0.0, locus=L['num'], side=side)
            if b:
                used.append(b)
    # roman-numeral groups: no placement hint; left-over candidates in reading order, low confidence
    leftover = [c for c in free if not overlaps(c['box'], used)]
    for name, loci_r in groups['roman'].items():
        items = label_items(loci_r)
        res = assign_group(items, leftover, per_glyph, 0, 0, hypotheses=('reading',))
        conf = min(0.3, res.get('confidence', 0))
        for it, b in zip(items, res['boxes']):
            put(it['token'], b, 'roman-group', conf, locus=it['locus'], group=name)
        leftover = [c for c in leftover if not any(b and c['box'] == b for b in res['boxes'])]
        log('group %s: %d tokens, matched %d (unverified placement, confidence %.2f)' % (name, len(items), res.get('matched', 0), conf))
    for L in groups['other']:
        for t in L['tokens']:
            put(t, None, 'unplaced', 0.0, locus=L['num'])
    scale = layout['image'].get('display_scale', 0.25)
    for r in records.values():
        r['display_box'] = [int(round(v * scale)) for v in r['box']] if r['box'] else None
    located = sum(1 for r in records.values() if r['box'])
    floor = layout.get('confidence_floor', 0.35)
    usable = sum(1 for r in records.values() if r['box'] and r['confidence'] >= floor)
    log('tokens %d, boxed %d, at or above the confidence floor %.2f: %d' % (len(records), located, floor, usable))
    return dict(page=layout.get('page', 'fRos'), image=dict(layout['image'], display_width=int(round(W * scale)), display_height=int(round(H * scale))),
                per_glyph_px=round(per_glyph, 1), confidence_floor=floor, tokens=records, loci=[dict(num=L['num'], type=L['type'], comments=L['comments'],
                tokens=[t['id'] for t in L['tokens']]) for L in loci], geometry_kind='detected')


def write_display_image(image_path, out_path, scale: float = 0.25, quality: int = 80):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(image_path).convert('RGB')
    im.resize((int(round(im.size[0] * scale)), int(round(im.size[1] * scale))), Image.LANCZOS).save(out_path, quality=quality, optimize=True)
    return out_path


def draw_overlay(image_path, record: dict, out_path, scale: float = 0.25):
    """The display image with every placed box (colour by method, dashed-looking thin boxes for low confidence)."""
    import cv2
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(image_path).convert('RGB')
    im = im.resize((int(round(im.size[0] * scale)), int(round(im.size[1] * scale))), Image.LANCZOS)
    arr = np.array(im)
    colours = {'ring': (200, 0, 0), 'spiral': (160, 0, 160), 'label': (0, 0, 220), 'label-block': (0, 90, 200), 'clock-label': (0, 140, 140), 'roman-group': (120, 120, 0)}
    for tid, r in record['tokens'].items():
        if not r['box']:
            continue
        b = [int(round(v * scale)) for v in r['box']]
        col = colours.get(r['method'], (0, 0, 0))
        cv2.rectangle(arr, (b[0], b[1]), (b[2], b[3]), col, 2 if r['confidence'] >= record['confidence_floor'] else 1)
    Image.fromarray(arr).save(out_path, quality=85)
    return out_path
