"""The atlas's built-in line, baseline and warp measures: ``vmsspatial.line_stats`` packaged for the viewer.

The atlas's Colors menu offers, under the heading "Lines, baselines and warp", the numbers of ``line_stats`` (the same
keys: ``colors=m:<key>`` in the address), its Overlays the lines and markers behind them, and a click on a word the
line's notes. They reach the manuscript bundle (viewer/data/manuscript/words.json.gz) through the fields a study's data
folder uses (``viewer_data.study_data``, whose measures keep the heading "From this text"): `measures`, `overlays`,
`line_notes`. Nothing is computed here. To read a number from code, call ``line_stats.line_table`` or ``word_table``.

Compact fields, all documented in ``viewer_data``: a per-line measure ships one value per line (`line_values`, expanded
by the atlas); `line_note_fields` names the measures shown in a line's notes, so the notes do not repeat their numbers;
`page_notes` holds what a page shares; an overlay's titles are built in the browser from `line` and `info` (only breaks
and intrusions need `info`); baseline anchors are one offset per rectangle (`anchors`, the anchor below the box bottom,
px), drawn at the box centre in the state shown. Overlay items carry recorded `points` and `points_flat`; a marker with
`token` moves with that token's box. Coordinates are rounded to 0.1 px.
"""
from __future__ import annotations

import gzip
import json
from typing import Dict, List, Optional

from .line_stats import GROUP, KEYS, LINE_KEYS, PAGE_KEYS, TOKEN_KEYS, VERSION, compute, values_of

# the line notes that are measures: (label, key, signed, unit)
NOTE_FIELDS = (('chord flat', 'chord_flat', 1, 'deg'), ('chord recorded', 'chord_recorded', 1, 'deg'), ('minus page median', 'chord_centred', 1, 'deg'), ('fit angle', 'ls_angle', 1, 'deg'),
               ('end offset', 'offset', 1, 'H'), ('minus page tilt', 'offset_centred', 1, 'H'), ('fit RMS', 'fit_rms', 0, 'H'), ('fit max |residual|', 'fit_max', 0, 'H'), ('at position', 'max_u', 0, ''),
               ('chord RMS', 'chord_rms', 0, 'H'), ('chord max |residual|', 'chord_max', 0, 'H'), ('sag', 'sag', 1, 'H'), ('second minus first half slope', 'half_diff', 1, 'H'), ('accumulation rho', 'rho', 1, ''),
               ('offset share at mid-line', 'mid_share', 0, ''), ('largest jump share', 'jump_share', 0, ''), ('jitter', 'jitter', 0, 'H'), ('words', 'line_words', 0, ''), ('span', 'line_span', 0, 'H'),
               ('warp on this line', 'warp_mean', 1, 'H'), ('warp range', 'warp_range', 0, 'H'), ('x-height', 'xheight', 0, 'H'), ('x-height spread', 'xheight_spread', 0, 'H'), ('ink fit RMS', 'ink_rms', 0, 'H'),
               ('ink minus box angle', 'ink_vs_box_angle', 1, 'deg'), ('clean ink words', 'ink_clean', 0, ''), ('local shift x', 'reg_dx', 1, 'px'), ('local shift y', 'reg_dy', 1, 'px'))
OVERLAY_NOTES = dict(
    chords='The chord from the first to the last baseline anchor of every horizontal line, in the state shown.',
    fits='The least-squares line through the anchors of every line with three or more, fitted in the state shown.',
    anchors="One marker per located rectangle at its baseline anchor: the ink baseline on pages with clean ink records, the glyph-corrected box baseline elsewhere.",
    warp="Per fitted line the warped baseline of the stored page warp against the straight baseline the line was flattened to. In the flat state the warped curve has become straight and the recorded straight line is not drawn.",
    breaks='A tick at each illustration break: transcript marker, geometric segment boundary, or both. Hover for the two words, the step and the gap.',
    break_fits="At every break the fit of each text component over its own words and its extension across the break, fitted in the state shown.",
    intrusions='Descender bottoms that reach into the line below and ascender tops that reach into the line above, depth above 0. Hollow markers touch the other word. Measured on the Beinecke scan.',
    ink_fits="The robust straight fit through each line's clean ink baselines, three or more words. Measured on the Beinecke scan; the flat state moves the baselines with the stored warp and refits.")


def _r(v, nd):
    return None if v is None else round(float(v), nd)


def _pts(xs, ys, nd=1):
    return [[round(float(x), nd), round(float(y), nd)] for x, y in zip(xs, ys)]


def _item(folio, points, flat=None, **kw):
    """An overlay item with `points_flat` only where the state differs (a page without a fitted field does not)."""
    from .viewer_data import overlay_item
    return overlay_item(folio, points, points_flat=None if flat == points else flat, **kw)


def _paragraph(r: dict) -> Optional[str]:
    if not r.get('par_pos'):
        return None
    return r['par_pos'] if r['par_pos'] == 'single' else '%s, line %d of %d' % (r['par_pos'], r['par_index'], r['par_len'])


def _break_note(r: dict, breaks: List[dict]) -> str:
    if not r['n_breaks']:
        return 'none'
    parts = ['%s %+.2f H' % (b['kind'], b['step']) if b['step'] is not None else '%s, step undetermined' % b['kind'] for b in breaks]
    return '; '.join(parts) if parts else '%d, no step' % r['n_breaks']


def _page_note(page: dict) -> Dict[str, str]:
    out = {}
    if page['fitted']:
        amp = page['page_warp_amplitude']
        out['page warp'] = 'amplitude %s, tilt %+.2f deg, keystone %+.3f deg per H, stronger side %s, gutter %s, fitted on %s' % (
            '%.2f H' % amp if amp is not None else 'unknown', page['page_tilt'], page['page_keystone'], page['gutter_side'], page['expected_gutter'], page['page_baseline'])
    else:
        out['page warp'] = 'not fitted: %s' % (page['reason'] or 'no field')
    if page['page_anchors']:
        out['anchors'] = page['page_anchors']
    if page['page_median_angle'] is not None:
        out['page median angle'] = '%+.2f deg flat, %+.2f deg recorded' % (page['page_median_angle'], page['page_median_recorded'])
    reg = page.get('registration')
    if reg:
        out['registration'] = '%s, %s inliers, %.2f px' % (reg['method'], reg['n_inliers'], reg['residual_px'] or 0.0)
    return out


def _line_items(stats: dict, nd: int = 1) -> Dict[str, list]:
    """The overlays' items: chords, least-squares lines, the warped baselines, ticks and component fits at breaks."""
    chords, fits, warps, ticks, break_fits = [], [], [], [], []
    lines = stats['lines']
    for r in lines:
        if r is None or '_x' not in r:
            continue
        l, x, yr, yf = r['line'], r['_x'], r['_yr'], r['_yf']
        ends = [x[0], x[-1]]
        chords.append(_item(r['folio'], _pts(ends, [yr[0], yr[-1]], nd), _pts(ends, [yf[0], yf[-1]], nd), style='chord', line=l))
        fr, ff = r['_fit_recorded'], r['_fit_flat']
        if fr and ff:
            fits.append(_item(r['folio'], _pts(ends, [fr[0] * v + fr[1] for v in ends], nd), _pts(ends, [ff[0] * v + ff[1] for v in ends], nd), style='ls', line=l))
    for c in stats['warp_curves']:
        xs = list(c['x'])
        warps.append(_item(c['folio'], _pts(xs, c['warped'], nd), _pts([xs[0], xs[-1]], [c['flat'][0], c['flat'][-1]], nd), style='warp-fit', line=c['line']))
        warps.append(_item(c['folio'], _pts([xs[0], xs[-1]], [c['straight'][0], c['straight'][-1]], nd), style='warp-flat', line=c['line'], states=['recorded']))
    for b in stats['breaks']:
        r = lines[b['line']]
        l, x = b['line'], r['_x']
        step = _r(b['step'], 2)
        ticks.append(_item(b['folio'], _pts([b['tick_x']] * 2, b['tick_recorded'], nd), _pts([b['tick_x']] * 2, b['tick_flat'], nd), style='break-' + b['kind'], line=l,
                           info=[b['left_token'], b['right_token'], step, _r(b['gap_W'], 2)]))
        xl, xk, xr, xe = x[b['first_ix']], x[b['left_ix']], x[b['right_ix']], x[b['last_ix']]
        fit_r, fit_f = b['recorded'], b['flat']
        if fit_r['fit_left'] and fit_f['fit_left']:
            (sr, ar), (sf, af) = fit_r['fit_left'], fit_f['fit_left']
            break_fits.append(_item(b['folio'], _pts([xl, xk], [sr * xl + ar, sr * xk + ar], nd), _pts([xl, xk], [sf * xl + af, sf * xk + af], nd), style='fit', line=l))
            break_fits.append(_item(b['folio'], _pts([xk, xr], [sr * xk + ar, sr * xr + ar], nd), _pts([xk, xr], [sf * xk + af, sf * xr + af], nd), style='fit-ext', line=l))
        if fit_r['fit_right'] and fit_f['fit_right']:
            (sr, ar), (sf, af) = fit_r['fit_right'], fit_f['fit_right']
            break_fits.append(_item(b['folio'], _pts([xr, xe], [sr * xr + ar, sr * xe + ar], nd), _pts([xr, xe], [sf * xr + af, sf * xe + af], nd), style='fit', line=l))
            break_fits.append(_item(b['folio'], _pts([xr, xk], [sr * xr + ar, sr * xk + ar], nd), _pts([xr, xk], [sf * xr + af, sf * xk + af], nd), style='fit-ext', line=l))
    return dict(chords=chords, fits=fits, warp=warps, breaks=ticks, break_fits=break_fits)


def _ink_items(stats: dict, nd: int = 1) -> Dict[str, list]:
    from .viewer_data import overlay_item
    fits = [_item(f['folio'], _pts(f['x'], f['y'], nd), _pts(f['x'], f['y_flat'], nd), style='ink-fit', line=f['line']) for f in stats['ink_fits']]
    events = []
    for e in stats['intrusions']:
        events.append(overlay_item(e['folio'], [[round(float(e['x']), nd), round(e['y'], nd)]], style='intrusion-touch' if e['touched'] else 'intrusion', kind='marker', line=e['upper_line'], token=e['stroke_token'],
                                   info=[e['upper_token'], e['lower_token'], round(e['depth_H'], 2), _r(e.get('gap_H'), 2), 1 if e['direction'] == 'down' else 0]))
    return dict(ink_fits=fits, intrusions=events)


def builtin(app: Optional[dict] = None, ms=None, ink_product: Optional[dict] = None, log=print) -> dict:
    """The built-in measures, overlays and line notes of a manuscript bundle.

    Args:
        app: the bundle the numbers are computed on (default: the sensitivity geometry of the whole manuscript, which
            ``viewer_data.build`` passes; either warp state).
        ms: its Manuscript.
        ink_product: the ink product (default the shipped one; without it the ink measures are empty).
        log: a print-like callable or None.

    Returns:
        {measures, overlays, line_notes, line_note_fields, page_notes, anchors, overlay_default, line_stats_version,
        line_stats_note}: the fields ``attach`` adds to the bundle. Token and line indices are those of `app`.
    """
    from .frames import tags
    from .viewer_data import line_measure, measure, overlay
    stats = compute(app, ms, ink=ink_product, log=log)
    measures = {}
    for k in TOKEN_KEYS:
        d = KEYS[k]
        measures[k] = measure(d['label'], [_r(v, d['digits']) for v in values_of(stats, k)], unit=d['unit'], kind=d['kind'], domain=d['domain'], digits=d['digits'], description=d['description'], group=GROUP)
    bundle_lines = stats['rec']['lines']
    for k in LINE_KEYS:
        d = KEYS[k]
        vals = [None if r is None else _r(r.get(k), d['digits']) for r in stats['lines']]
        measures[k] = line_measure(d['label'], vals, unit=d['unit'], kind=d['kind'], domain=d['domain'], digits=d['digits'], description=d['description'], group=GROUP, menu=d['menu'])
    for k in PAGE_KEYS:
        d = KEYS[k]
        vals = [_r(stats['pages'][L['page']][k], d['digits']) for L in bundle_lines]
        measures[k] = line_measure(d['label'], vals, unit=d['unit'], kind=d['kind'], domain=d['domain'], digits=d['digits'], description=d['description'], group=GROUP)
    by_line: Dict[int, List[dict]] = {}
    for b in stats['breaks']:
        by_line.setdefault(b['line'], []).append(b)
    notes: List[Optional[dict]] = [None] * len(stats['lines'])
    for l, r in enumerate(stats['lines']):
        if r is None:
            continue
        note = {'line': '%s.%s' % (r['folio'], r['locus'])}
        para = _paragraph(r)
        if para:
            note['paragraph'] = para
        if r['chord_flat'] is not None:
            note['breaks'] = _break_note(r, by_line.get(l, []))
        notes[l] = note
    # the anchors: one offset per rectangle from the box bottom, on its first token
    anchors: List[Optional[float]] = [None] * stats['n_tokens']
    for w in stats['words']:
        if w['kind'] == 'horizontal' and w['anchor'] != 'box centre':
            anchors[w['first']] = round(w['y_recorded'] - w['y1'], 1)
    items = _line_items(stats)
    items.update(_ink_items(stats))
    src = tags(stats['rec'])['source']
    tag = dict(frame='recorded', warp='recorded')
    overlays = dict(
        chords=overlay('Chords', items['chords'], OVERLAY_NOTES['chords'], source=src, **tag),
        fits=overlay('Line fits', items['fits'], OVERLAY_NOTES['fits'], source=src, **tag),
        anchors=overlay('Baseline anchors', [], OVERLAY_NOTES['anchors'], source=src, markers_from='anchors', r=2, **tag),
        warp=overlay('Page warp', items['warp'], OVERLAY_NOTES['warp'], source=src, **tag),
        breaks=overlay('Breaks', items['breaks'], OVERLAY_NOTES['breaks'], source=src, **tag),
        break_fits=overlay('Break fits', items['break_fits'], OVERLAY_NOTES['break_fits'], source=src, **tag),
        intrusions=overlay('Intrusions', items['intrusions'], OVERLAY_NOTES['intrusions'], source='beinecke', **tag),
        ink_fits=overlay('Ink fits', items['ink_fits'], OVERLAY_NOTES['ink_fits'], source='beinecke', **tag))
    note = 'vmsspatial.line_stats %s: anchors %s, %d horizontal lines, %d with a chord, %d with a fit, %s.' % (
        VERSION, stats['baseline_pages'], sum(1 for r in stats['lines'] if r), sum(1 for r in stats['lines'] if r and r['chord_flat'] is not None),
        sum(1 for r in stats['lines'] if r and r['ls_angle'] is not None), stats['ink_note'])
    return dict(measures=measures, overlays=overlays, line_notes=notes, line_note_fields=[list(f) for f in NOTE_FIELDS], page_notes={f: _page_note(p) for f, p in stats['pages'].items()},
                anchors=anchors, overlay_default='none', line_stats_version=VERSION, line_stats_note=note)


def gz_size(value) -> int:
    """Bytes of `value` in the bundle's own encoding, gzipped alone."""
    return len(gzip.compress(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode('utf-8'), mtime=0))


def sizes(extras: dict) -> Dict[str, int]:
    """Gzipped bytes per group of the built-in fields, for the release report."""
    out = {'word measures': gz_size({k: v for k, v in extras['measures'].items() if 'values' in v}), 'line measures': gz_size({k: v for k, v in extras['measures'].items() if 'line_values' in v}),
           'line notes': gz_size([extras['line_notes'], extras['line_note_fields'], extras['page_notes']]), 'anchors': gz_size(extras['anchors'])}
    for k, o in extras['overlays'].items():
        out['overlay ' + k] = gz_size(o)
    return out


def attach(bundle: dict, app: Optional[dict] = None, ms=None, ink_product: Optional[dict] = None, log=print) -> dict:
    """A copy of the atlas bundle with the built-in fields, computed on `app` (the same token stream under another
    policy; ``viewer_data.build`` passes the sensitivity geometry, the most complete reviewed one)."""
    from .bundle import digest
    extras = builtin(app, ms, ink_product, log)
    source = app if app is not None else bundle
    if digest(bundle['words']) != digest(source['words']) or len(bundle['lines']) != len(source['lines']):
        raise ValueError('the bundle and the bundle the measures were computed on have different streams')
    if log:
        s = sizes(extras)
        log('line measures: ' + extras['line_stats_note'])
        log('line measures, gzipped bytes alone: ' + ', '.join('%s %d' % kv for kv in s.items()) + '; total %.2f MB' % (sum(s.values()) / 2 ** 20))
    return dict(bundle, **extras)
