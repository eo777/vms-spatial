"""Data for the viewer (viewer/data): bundles plus a layout record with page sizes, orders and labels.

    vmsspatial viewer-data                                   # the whole recorded manuscript (strict geometry, by bifolium, flat measures) + the review
    vmsspatial viewer-data --control markov:section --control stream:timm_spatial --control prose_native:de_gart_augsburg1487
    vmsspatial viewer-data --order path1                     # a second manuscript bundle whose token stream follows the Path 1 order

The default bundle is ``load_bundle('strict')``: every page and locus, by bifolium, the flat warp state; the viewer
DRAWS the recorded rectangles (the review's parts, or ``geometry_recorded`` for a bundle without a review) on the
page images and COMPUTES the spatial measures from ``geometry`` (flat); its Coordinates control draws the flat state
instead, except on a page image. Control bundles are typeset into the study text's recorded line frames and flattened
the same way. The manuscript bundle also carries the built-in line, baseline and warp measures, overlays and line notes
(``vmsspatial.viewer_measures``, in the fields a study's data folder uses).

    study_data(out_dir, bundle, key, label, measures=, overlays=, line_notes=)   # a study's own data folder for the same viewer

Writes viewer/data/index.json ({bundles: [{key, label, path, order, tokens}], layout, review}), viewer/data/layout.json.gz
(pages, nodes, orders, groups, sections) and viewer/data/<key>/words.json.gz. The review file is not copied: index.json
names it where it lies (data/manuscript/spatial_review.json.gz, relative to the viewer's data folder).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import paths
from .bundle import load_bundle, make_bundle, read_json, rounded_geometry, save_bundle, write_json
from .manuscript import DEFAULT_ORDER, GROUP_ORDER, GROUP_SECTION, ORDERS, Manuscript, load_order, page_key
from .units import COMPONENT_MODES

VIEWER_DIR = paths.TOOLKIT / 'viewer'


def node_labels(ms: Manuscript) -> Dict[str, dict]:
    """Section label per bifolium from the pages' section letters (generic text-only pages do not replace a named section)."""
    out = {}
    for n in ms.nodes:
        sections, detail = [], []
        for p in n['pages']:
            name = ms.physical[p]['section_name']
            detail.append(p + ': ' + name)
            if name not in sections:
                sections.append(name)
        named = [s for s in sections if s != 'Text'] or sections
        out[n['id']] = dict(label=' + '.join(named) + ' / ' + n['group'], detail='; '.join(detail), sections=sections)
    return out


def with_recorded(bundle: dict) -> dict:
    """The bundle with ``geometry_recorded`` beside its (flat) ``geometry``: what the viewer draws on the page images.
    A bundle already in the recorded state gets a copy of its geometry."""
    from .frames import tags
    out = dict(bundle)
    if tags(bundle)['warp'] == 'flat':
        from .warp import transform
        out['geometry_recorded'] = transform(bundle, 'recorded')['geometry']
    else:
        out['geometry_recorded'] = list(bundle['geometry'])
    out['drawn'] = 'recorded'
    out['measured'] = tags(bundle)['warp']
    return out


def layout_record(ms: Manuscript, review: Optional[dict] = None, supplement: Optional[dict] = None) -> dict:
    """Page sizes, images, nodes, orders and leaves for the viewer. A page of the detected-geometry supplement (the
    Rosettes) is self-hosted: its image is the toolkit's quarter-scale copy and its boxes are in that image's frame."""
    pages = {}
    if supplement is None:
        sp = paths.resolve('manuscript/supplement_fRos.json', required=False)
        supplement = read_json(sp) if sp and Path(sp).exists() else None
    sup_page = (supplement or {}).get('page')
    for p in ms.pages:
        info = (review or {}).get('pages', {}).get(p['folio']) if review else None
        if info is None and supplement and p['folio'] == sup_page:
            im = supplement['image']
            pages[p['folio']] = dict(width=im['display_width'], height=im['display_height'], missing=False, image='img/%s.jpg' % sup_page, self_hosted=True,
                                     image_source=im.get('source'), geometry_kind='detected', node=p['node'], group=p['group'], leaf=p['leaf'], side=p['side'],
                                     quire=p['quire'], quire_num=p['quire_num'], bifolium=p['bifolium'], bif_pos=p['bif_pos'], section=p['section'],
                                     section_name=p['section_name'], currier=p['currier'], hand=p['hand'], face=p['face'])
            continue
        pages[p['folio']] = dict(width=info['width'] if info else 1100, height=info['height'] if info else 1500, missing=info is None,
                                 image=info.get('display_image') if info else None, node=p['node'], group=p['group'], leaf=p['leaf'], side=p['side'],
                                 quire=p['quire'], quire_num=p['quire_num'], bifolium=p['bifolium'], bif_pos=p['bif_pos'], section=p['section'],
                                 section_name=p['section_name'], currier=p['currier'], hand=p['hand'], face=p['face'])
    labels = node_labels(ms)
    nodes = [dict(id=n['id'], group=n['group'], N=n['N'], pages=n['pages'], label=labels[n['id']]['label'], detail=labels[n['id']]['detail'], sections=labels[n['id']]['sections']) for n in ms.nodes]
    orders = {name: [n['id'] for n in (Manuscript.load(name, pages='all').nodes if ms.extra else load_order(name))] for name in ('bifolia', 'path1')}
    folio_pages = [p['folio'] for p in sorted(ms.pages, key=lambda p: page_key(p['folio'], p))]
    by_leaf = {}
    for p in ms.pages:
        by_leaf.setdefault((p['leaf'], p['panel']), []).append(p['folio'])
    leaves = [dict(leaf=k[0], panel=k[1], pages=sorted(v, key=lambda f: ms.physical[f]['side'])) for k, v in sorted(by_leaf.items(), key=lambda kv: (ms.physical[kv[1][0]]['quire_num'], kv[0][0], kv[0][1]))]
    sections = sorted({p['section_name'] for p in ms.pages})
    return dict(order=ms.order, pages=pages, nodes=nodes, orders=orders, folio_pages=folio_pages, leaves=leaves, groups=GROUP_ORDER, group_section=GROUP_SECTION, sections=sections)


def build(out_dir=None, controls: Optional[List[str]] = None, order=DEFAULT_ORDER, policy='strict', ms=None, review=None, log=print, extra=True, warp='flat', compare=True, line_stats=True) -> dict:
    """The viewer's data: the manuscript bundle (every page and locus unless extra=False, the chosen order, the flat
    warp state unless warp='recorded'; ``geometry_recorded`` beside it for drawing), with the built-in line, baseline
    and warp measures unless line_stats=False (``viewer_measures.attach``), the control bundles (typeset into the study
    text's recorded line frames in the same order, then moved to the same warp state), the layout and, unless
    compare=False, the comparison extras (``compare_data``: units with anchors and flat shifts, blocks, breaks, wheels,
    orders, pair rankings)."""
    from .audit.review import load_review
    from .controls import build_control
    from .geometry import line_frames
    out = Path(out_dir) if out_dir else VIEWER_DIR / 'data'
    out.mkdir(parents=True, exist_ok=True)
    pages = 'all' if extra else 'paragraph'
    ms_study = ms or Manuscript.load(order, pages='paragraph')
    ms_full = Manuscript.load(order, pages=pages)
    review = review or load_review()
    app = with_recorded(load_bundle(policy, pages=pages, order=order, warp=warp))
    sens = load_bundle('sensitivity', pages=pages, order=order, warp='recorded') if line_stats or compare else None      # the most complete reviewed geometry
    if line_stats:
        from .viewer_measures import attach
        app = attach(app, sens, ms_full, log=log)
    index = dict(bundles=[])
    key = 'manuscript' if order == DEFAULT_ORDER else 'manuscript_%s' % order
    (out / key).mkdir(exist_ok=True)
    save_bundle(app, out / key / 'words.json.gz')
    index['bundles'].append(dict(key=key, label='Manuscript (%s geometry, %s order%s)' % (policy, order, ', measures in the flat state' if warp == 'flat' else ''),
                                 path=key + '/words.json.gz', order=order, tokens=len(app['words']), components=app['component_mode'], warp=warp, pages=pages))
    log('wrote %s' % key)
    if controls:
        base = load_bundle('sensitivity', pages='paragraph', order=order, warp='recorded')      # the most complete reviewed geometry: the line frames the controls are typeset into
        frames = line_frames(base, ms_study)
        for spec in controls:
            kind, _, name = spec.partition(':')
            lines, geometry, comp, info = build_control(ms_study, base, kind, name or None, frames=frames)
            b = make_bundle(ms_study, lines, rounded_geometry(geometry), comp, provenance=base['geometry_provenance'], palette=app.get('palette'),
                            geometry_kind=info['geometry_kind'], passage={k: v for k, v in info.items() if k != 'geometry_kind'})
            if warp == 'flat':
                from .warp import transform
                flat_b = transform(b, 'flat')
                flat_b['geometry_recorded'] = b['geometry']
                flat_b['drawn'], flat_b['measured'] = 'recorded', 'flat'
                b = flat_b
            ck = (kind + '_' + name).replace(':', '_') if name else kind
            (out / ck).mkdir(exist_ok=True)
            save_bundle(b, out / ck / 'words.json.gz')
            index['bundles'].append(dict(key=ck, label=control_label(kind, name), path=ck + '/words.json.gz', order=order, tokens=len(b['words']), components=b['component_mode'], warp=warp, pages='paragraph'))
            log('wrote %s' % ck)
    write_json(layout_record(ms_full, review), out / 'layout.json.gz')
    sup_img = VIEWER_DIR / 'img' / 'fRos.jpg'
    if extra and not sup_img.exists():
        log('note: viewer/img/fRos.jpg is missing; run scripts/rosettes_geometry.py --display viewer/img/fRos.jpg for the Rosettes image')
    review_path = review_location(out)
    existing = {}
    if (out / 'index.json').exists():
        try:
            existing = {b['key']: b for b in json.loads((out / 'index.json').read_text(encoding='utf-8'))['bundles']}
        except (ValueError, KeyError):
            existing = {}
    for b in index['bundles']:
        existing[b['key']] = b
    bundles = [b for b in existing.values() if (out / b['path']).exists()]
    bundles.sort(key=lambda b: (b['key'] != key, b['key'] != 'manuscript', b['key']))
    index = dict(bundles=bundles, layout='layout.json.gz', review=review_path, default_order=order)
    (out / 'index.json').write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8')
    if compare:
        index['compare'] = compare_data(out, app=sens, ms=ms_full, bundle_key=key, log=log)
    return index


def review_location(out: Path) -> str:
    """Where the viewer finds the alignment review, relative to its data folder: the shipped file in data/manuscript when
    both lie inside the toolkit folder (the GitHub Pages layout), otherwise a copy beside the bundles."""
    src = Path(paths.resolve('manuscript/spatial_review.json.gz')).resolve()
    out = Path(out).resolve()
    toolkit = paths.TOOLKIT.resolve()
    if str(src).startswith(str(toolkit)) and str(out).startswith(str(toolkit)):
        return os.path.relpath(src, out).replace('\\', '/')
    shutil.copyfile(src, out / 'spatial_review.json.gz')
    return 'spatial_review.json.gz'


def default_palette() -> list:
    """The viewer's 501-colour diversity scale (warm = low, teal = high)."""
    p = json.loads(paths.resource('palette.json').read_text(encoding='utf-8'))
    return p if isinstance(p, list) else next(v for v in p.values() if isinstance(v, list))


def measure(label, values, unit='', kind='sequential', domain=None, digits=2, description='', per='token', group=None):
    """A per-token measure for the viewer's Colors menu: one number (or None) per token of the bundle. kind 'sequential'
    (warm = low, teal = high) or 'diverging' (symmetric about zero); domain fixes the colour range, else the 5-95% range
    of the values is used. per='line' marks a per-line statistic broadcast to the line's tokens (`per_line`), so the
    viewer's row means weight every line once instead of every word. `group` is the heading in the Colors menu
    (default "From this text")."""
    if kind not in ('sequential', 'diverging'):
        raise ValueError("kind must be 'sequential' or 'diverging'")
    if per not in ('token', 'line'):
        raise ValueError("per must be 'token' or 'line'")
    vals = [None if v is None or (isinstance(v, float) and v != v) else float(v) for v in values]
    out = dict(label=label, unit=unit, kind=kind, values=vals, digits=int(digits), description=description, per=per)
    if domain is not None:
        out['domain'] = [float(domain[0]), float(domain[1])]
    if group:
        out['group'] = group
    return out


def line_measure(label, line_values, unit='', kind='sequential', domain=None, digits=2, description='', group=None, menu=True):
    """A per-line measure stored compactly: one number (or None) per line of the bundle, under `line_values`. The atlas
    expands it to per-token `values` when it loads the bundle, so the legend and the row means work as for `measure`,
    and the row means stay line-weighted (per='line'). `menu=False` keeps it out of the Colors menu: its values still
    serve the line notes (`line_note_fields`) and the overlay titles."""
    m = measure(label, [], unit=unit, kind=kind, domain=domain, digits=digits, description=description, per='line', group=group)
    del m['values']
    m['line_values'] = [None if v is None or (isinstance(v, float) and v != v) else float(v) for v in line_values]
    if not menu:
        m['menu'] = False
    return m


def per_line(bundle, line_values):
    """Per-token values from per-line values (every token of a line takes its line's value), for `measure`."""
    if len(line_values) != len(bundle['lines']):
        raise ValueError('%d line values for %d lines' % (len(line_values), len(bundle['lines'])))
    out = [None] * len(bundle['words'])
    for L, v in zip(bundle['lines'], line_values):
        for i in range(L['start'], L['end']):
            out[i] = v
    return out


def overlay_item(page, points, style='line', kind='polyline', title=None, line=None, r=None, points_flat=None, states=None, token=None, info=None):
    """One drawn element in a page's coordinate frame (the frame of the bundle's boxes): a polyline through `points`
    ([[x, y], ...]) or, with kind='marker', a dot at points[0]. style is a CSS token the viewer knows (line, chord, ls
    (a whole-line fit), fit and fit-ext (a component's fit and its extension across a break), break-transcript,
    break-geometric, break-both (hoverable ticks; put the numbers in `title`), baseline, marker, warp-fit, warp-flat,
    ink-fit, intrusion, intrusion-touch) or any other word for custom styling.

    `points_flat` holds the same element in the flat warp state, beside recorded `points`, where the two differ; a
    marker with `token` instead moves with that token's box. `states` (['recorded'] or ['flat']) limits the element to
    one state: it is skipped in the other. `info` is a short list the atlas turns into the element's title."""
    if kind not in ('polyline', 'line', 'marker'):
        raise ValueError("kind must be 'polyline', 'line' or 'marker'")
    if states is not None and not set(states) <= {'recorded', 'flat'}:
        raise ValueError("states must name 'recorded' or 'flat'")
    item = dict(page=page, points=[[float(x), float(y)] for x, y in points], style=style, kind=kind)
    if points_flat is not None:
        item['points_flat'] = [[float(x), float(y)] for x, y in points_flat]
    if states is not None:
        item['states'] = list(states)
    if token is not None:
        item['token'] = int(token)
    if info is not None:
        item['info'] = list(info)
    if title is not None:
        item['title'] = str(title)
    if line is not None:
        item['line'] = int(line)
    if r is not None:
        item['r'] = float(r)
    return item


def overlay(label, items, description='', frame=None, warp=None, source=None, markers_from=None, r=None):
    """A named set of overlay items for the viewer's Page overlay > Overlays control. `frame`, `warp` and `source`
    tag the coordinates the items are in (``vmsspatial.frames``); without them the overlay is taken to be in the
    bundle's state when ``study_data`` writes it. An overlay meant for the page image must be recorded / recorded.
    `markers_from` names a per-token field of the bundle: the vertical offset of a marker from its box's bottom, drawn
    at the box's centre x with radius `r` in the state shown, instead of one stored item per word."""
    for it in items:
        if 'page' not in it or 'points' not in it:
            raise ValueError('an overlay item needs page and points (use overlay_item)')
    out = dict(label=label, description=description, items=list(items))
    if markers_from:
        out['markers_from'] = markers_from
    if r is not None:
        out['r'] = float(r)
    if frame or warp or source:
        from .frames import tag
        tag(out, frame=frame, warp=warp, source=source)
    return out


def _moved_point(it: dict, x: float, y: float, bundle: dict, to: str, prod: dict) -> float:
    """y of one overlay point in the warp state `to`: by its page and, when the item names a bundle `line`, that line's
    locus (else the page's full field at the point's own height). A point on a page without a fitted field, or on a
    line the warp does not move (not horizontal), keeps its y, as the boxes do."""
    from .warp import _moves, apply as warp_apply
    locus = str(bundle['lines'][it['line']]['locus']) if it.get('line') is not None and it['line'] < len(bundle['lines']) else ''
    rec = prod['pages'].get(it['page'])
    if not rec or not rec.get('fitted') or (locus and not _moves(rec, locus)):
        return float(y)
    return float(warp_apply(it['page'], x, y, locus, to, prod))


def overlay_to_recorded(o: dict, bundle: dict) -> dict:
    """An overlay in the flat warp state moved to recorded coordinates (``warp.apply``), its flat points kept beside
    them as `points_flat` so that the atlas can draw either state."""
    from .warp import load_warp
    prod = load_warp()
    items = [dict(it, points=[[float(x), _moved_point(it, x, y, bundle, 'recorded', prod)] for x, y in it['points']], points_flat=[[float(x), float(y)] for x, y in it['points']]) for it in o['items']]
    return dict(o, items=items, warp='recorded', converted_from='flat')


def overlay_with_flat(o: dict, bundle: dict) -> dict:
    """A recorded overlay on a bundle that also draws the flat state: `points_flat` added to every item that lacks it
    (``warp.apply``), so that nothing stays in recorded coordinates over flat boxes."""
    from .warp import load_warp
    prod = load_warp()
    items = [it if 'points_flat' in it or 'token' in it else dict(it, points_flat=[[float(x), _moved_point(it, x, y, bundle, 'flat', prod)] for x, y in it['points']]) for it in o['items']]
    return dict(o, items=items)


def _reference(src: Path, out: Path, name: str) -> str:
    """Name `src` from the data folder `out`: a relative path when both can be served from one root, else a copy."""
    src, out = Path(src).resolve(), Path(out).resolve()
    try:
        rel = os.path.relpath(src, out).replace('\\', '/')
    except ValueError:                                      # another drive
        rel = None
    if rel is not None and rel.count('../') <= 6:
        return rel
    shutil.copyfile(src, out / name)
    return name


def study_data(out_dir, bundle: dict, key: str, label: str, measures: Optional[dict] = None, overlays: Optional[dict] = None,
               line_notes: Optional[list] = None, layout_url: Optional[str] = None, review_url: Optional[str] = None, log=print) -> dict:
    """A viewer data folder for a study, read by the toolkit's own atlas (viewer/index.html#data=<url of out_dir>): one
    bundle (the words, lines and geometry it was scored on) carrying the study's `measures` ({key: measure(...)}),
    `overlays` ({key: overlay(...)}) and `line_notes` (per line, a {label: value} dict or None, shown when a word is
    clicked), and an index.json that names the toolkit's layout and review files instead of copying them (relative
    paths by default; give URLs for a hosted study). Nothing of the viewer is copied: the study ships data only. Address
    keys for links: colors=m:<measure key>, expanded=<folio>, line=<locus>, overlays=<key|all|none>, image=1, words=1."""
    from .frames import ensure_tags, require_same, tags as frame_tags
    out = Path(out_dir)
    (out / key).mkdir(parents=True, exist_ok=True)
    b = ensure_tags(dict(bundle))
    n = len(b['words'])
    if measures:
        for k, m in measures.items():
            if 'line_values' in m:
                if len(m['line_values']) != len(b['lines']):
                    raise ValueError('measure %r has %d line values for %d lines' % (k, len(m['line_values']), len(b['lines'])))
            elif len(m['values']) != n:
                raise ValueError('measure %r has %d values for %d tokens' % (k, len(m['values']), n))
        b['measures'] = measures
    if frame_tags(b)['warp'] == 'flat':
        b = with_recorded(b)                                     # the viewer draws recorded rectangles and measures the flat ones
    if overlays:
        pages = {L['page'] for L in b['lines']}
        tagged = {}
        for k, o in overlays.items():
            for it in o['items']:
                if it['page'] not in pages:
                    raise ValueError('overlay %r names page %s, which the bundle does not cover' % (k, it['page']))
            o = dict(o)
            if not any(o.get(t) for t in ('frame', 'warp', 'source')):
                t = frame_tags(b)
                o.update(frame=t['frame'], warp=t['warp'], source=t['source'])
            if frame_tags(o)['frame'] != frame_tags(b)['frame']:
                require_same(b, o, 'the bundle and overlay %r' % k)
            if frame_tags(o)['warp'] == 'flat':
                # overlays are drawn on the page images: converted to recorded coordinates here, explicitly
                o = overlay_to_recorded(o, b)
            elif 'geometry_recorded' in b and frame_tags(b)['warp'] == 'flat':
                o = overlay_with_flat(o, b)                      # the atlas can draw this bundle flat: the overlay follows
            tagged[k] = o
        b['overlays'] = tagged
    if line_notes is not None:
        if len(line_notes) != len(b['lines']):
            raise ValueError('%d line notes for %d lines' % (len(line_notes), len(b['lines'])))
        b['line_notes'] = line_notes
    if not b.get('palette'):
        b['palette'] = default_palette()
    save_bundle(b, out / key / 'words.json.gz')
    if layout_url is None:
        layout_file = VIEWER_DIR / 'data' / 'layout.json.gz'
        if not layout_file.exists():
            from .audit.review import load_review
            layout_file = out / 'layout.json.gz'
            write_json(layout_record(Manuscript.load(b.get('order') if b.get('order') in ORDERS else DEFAULT_ORDER, pages='all'), load_review()), layout_file)
        layout_url = _reference(layout_file, out, 'layout.json.gz')
    if review_url is None:
        review_url = _reference(Path(paths.resolve('manuscript/spatial_review.json.gz')), out, 'spatial_review.json.gz')
    index = dict(bundles=[dict(key=key, label=label, path=key + '/words.json.gz', order=b.get('order') or DEFAULT_ORDER, tokens=n, components=b.get('component_mode', ''),
                               warp=frame_tags(b)['warp'], pages=b.get('pages'))],
                 layout=layout_url, review=review_url, default_order=b.get('order') or DEFAULT_ORDER)
    (out / 'index.json').write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8')
    log('wrote %s: %d tokens, %d measures, %d overlays; open the atlas with #data=<url of %s>' % (out / key, n, len(measures or {}), len(overlays or {}), out))
    return index


COMPARE_VERSION = '2026.10.31.1'
UNIT_FLAG_INTRUSION, UNIT_FLAG_CLEAN, UNIT_FLAG_BOX_CENTRE, UNIT_FLAG_GROUPED = 1, 2, 4, 8
COMPARE_FIELDS = dict(
    pages='{folio: page}; token indices refer to the atlas manuscript bundle named in `bundle` (same stream for every policy)',
    page='node, section, hand, group, slot (Ar|Av|Br|Bv), face (inner|outer), leaf, side, panel, quire_num, H and W (median body box height and width, px), warp_fitted, geometry_kind (recorded|detected), frame',
    lines='[[locus, first (1 = paragraph start), category (P|L|C|R|?), orientation kind]] indexed by page line index',
    blocks='[[key, [page line indices]]]: opening (first five paragraph lines), page (all), p1.. (canonical paragraphs), l<i> (each non-paragraph locus)',
    units='[[first, last, line, x0, y0, x1, y1, dy, bx, by, flags]]: token range (inclusive) in the bundle, page line index, recorded rectangle, dy = recorded bottom - flat bottom '
          '(flat rectangle = rectangle moved up by dy; 0 where the warp does not move the line), recorded baseline anchor (bx, by; flat anchor y = by - dy), '
          'flags: 1 intrusion boundary after the unit, 2 clean (one unflagged word-level token), 4 anchor is the box centre (no baseline: non-horizontal line), 8 grouped (several tokens in one rectangle). '
          'Units are in reading order per line (left to right on horizontal lines). Text = bundle words[first..last] joined by spaces; atoms = compare_math.atoms(text).',
    breaks='[[line, left unit id, right unit id, kind]]: the intrusion breaks of geometry.line_breaks (kind 1 transcript <-> or <~>, 2 geometric gap, 3 both) whose right word lies right of the left word',
    paper='{mm, fold, top, fold_method, top_method, scale_method}: the page on the parchment (vmsspatial.leaves, data/manuscript/leaves.json.gz): recorded px per mm, recorded x of the fold '
          '(where the leaf meets the binding) and recorded y of the leaf top edge, each measured on the Beinecke scan or estimated; absent for a page with no located box',
    drift='{recorded: {angle, slope, n, dropped, unavailable}, flat: {...}, lines: [[line, angle_recorded, angle_flat, units, span, qualifies]], method, source}: '
          'the drift indicator (compare.page_drift). angle = median signed first-to-last baseline chord angle (degrees, positive falls right) over the qualifying horizontal '
          'paragraph lines (at least 4 located boxes spanning 3 median word widths, both endpoints baseline anchors); recorded = pre-correction (the workspace\'s guide), '
          'flat = the same chords after the stored page warp; lines lists every horizontal paragraph line with two baseline-anchored boxes (angles null where an endpoint is a box centre); '
          'the guide through the comparison origin is [[x0, slope*gain*x0], [x1, slope*gain*x1]] and is illustrative, not a fitted intercept',
    coordinates='recorded = the rectangles as given; flat = y - dy for every edge and the anchor. Nothing drawn on a page image may use the flat state.',
    anchors='the baseline method of the Python export (`baseline`), one point per unit; the alignment translates a block so that its first unit anchor is the origin (starts) or the page opening anchor (page)')


def _round(v, nd=2):
    return None if v is None else round(float(v), nd)


def compare_data(out_dir=None, app=None, ms=None, baseline='auto', top=50, bundle_key='manuscript', log=print, scan=True) -> dict:
    """The comparison extras of the atlas (viewer/data/compare): per page the units with their recorded rectangles,
    flat shifts and baseline anchors, the blocks, the break markers; the wheels; the orders; the first-line pair
    rankings (top `top` per page and per bifolium face). Derived from the sensitivity bundle in the recorded warp state
    (the most complete reviewed geometry, shared boxes once); token indices refer to the atlas bundle's stream, which is
    the same for every policy. Returns the index entry."""
    from . import compare as C
    from .bundle import load_bundle
    from .frames import tags
    from .wheels import wheels_for
    out = Path(out_dir) if out_dir else VIEWER_DIR / 'data'
    (out / 'compare').mkdir(parents=True, exist_ok=True)
    if ms is None:
        ms = Manuscript.load()
    if app is None:
        app = load_bundle('sensitivity', pages=ms.page_set, order=ms.order, warp='recorded')
    data = C.prepare(app, ms, baseline=baseline, log=log)
    from .leaves import load_leaves, for_viewer
    leaves = load_leaves()
    pages = {}
    for folio in data['folios']:
        p = data['pages'][folio]
        unit_id = {}
        units = []
        for u in p['units']:
            flags = (UNIT_FLAG_INTRUSION if u['boundary'] in C.INTRUSION else 0) | (UNIT_FLAG_CLEAN if u['clean'] else 0) | (UNIT_FLAG_BOX_CENTRE if u['anchor_kind'] == 'box centre' else 0) | (UNIT_FLAG_GROUPED if u['last'] > u['first'] else 0)
            unit_id[(u['first'], u['last'])] = len(units)
            units.append([u['first'], u['last'], u['line'], _round(u['rect'][0]), _round(u['rect'][1]), _round(u['rect'][2]), _round(u['rect'][3]),
                          _round(u['rect'][3] - u['flat'][3]), _round(u['base'][0]), _round(u['base'][1]), flags])
        breaks = [[m['line'], m['left'], m['right'], 1 if m['kind'] == 'transcript' else 3] for m in C.line_break_markers(data, folio) if m['located']]
        dr, df = C.page_drift(data, folio, 'recorded'), C.page_drift(data, folio, 'flat')
        flat_lines = {l['index']: l for l in df['lines']}
        drift = dict(recorded=dict(angle=_round(dr['angle'], 4), slope=_round(dr['slope'], 6), n=dr['n'], dropped=dr['dropped'], unavailable=dr['unavailable']),
                     flat=dict(angle=_round(df['angle'], 4), slope=_round(df['slope'], 6), n=df['n'], dropped=df['dropped'], unavailable=df['unavailable']),
                     lines=[[l['index'], _round(l.get('angle'), 4), _round(flat_lines.get(l['index'], {}).get('angle'), 4), l['units'], _round(l.get('span'), 2), 1 if l['qualifies'] else 0] for l in dr['lines']],
                     method=dr['method'], source=dr['source'])
        pages[folio] = dict(node=p['node'], section=p['section'], hand=p['hand'], group=p['group'], slot=p['slot'], face=p['face'], leaf=p['leaf'], side=p['side'], panel=p['panel'],
                            quire_num=p['quire_num'], H=p['H'], W=p['W'], warp_fitted=bool(p['warp']['fitted']), geometry_kind=p['geometry_kind'], frame=p['frame'],
                            lines=[[l['locus'], 1 if l['first'] else 0, l['category'], l['orientation']] for l in p['lines']],
                            blocks=[[b['key'], b['lines']] for b in p['blocks']], units=units, breaks=breaks, drift=drift)
        paper = for_viewer(leaves, folio)
        if paper:
            pages[folio]['paper'] = paper
        pages[folio]['_unit_id'] = unit_id
    t = tags(app)
    pages_out = {f: {k: v for k, v in p.items() if k != '_unit_id'} for f, p in pages.items()}
    quarantine = sorted(C._quarantine(data))
    write_json(dict(version=COMPARE_VERSION, bundle=bundle_key, frame=t['frame'], warp='recorded', source=t['source'], policy=app.get('policy'), baseline=baseline,
                    baseline_pages=data['baseline_pages'], page_warp_version=data['provenance']['page_warp_version'], provenance=data['provenance'], fields=COMPARE_FIELDS, quarantine=quarantine,
                    drift_pages=sum(1 for p in pages.values() if p['drift']['recorded']['angle'] is not None),
                    paper=dict(version=leaves['version'], catalogue=leaves['catalogue'], calibration=leaves['calibration'], medians=leaves['medians'], counts=leaves['counts']) if leaves else None,
                    note='Comparison extras of the atlas (vmsspatial.viewer_data.compare_data). Translation-only overlay scores describe resemblance, not copying; '
                         'a centred wheel composite is a display transform, not evidence (docs/PITFALLS.md 24, 25).',
                    pages=pages_out), out / 'compare' / 'pages.json.gz')
    # wheels: the shipped product with ring members as unit ids of the page
    prod = wheels_for(app, ms)
    wheels = {}
    for folio, rec in prod['pages'].items():
        if not rec['wheels'] and not rec['rejected']:
            continue
        pg = pages[folio]
        base = next(q['start_line'] for q in ms.pages if q['folio'] == folio)
        ws = []
        for w in rec['wheels']:
            ws.append(dict(id=w['id'], centre=[_round(w['centre'][0]), _round(w['centre'][1])], radius=_round(w['radius']), centre_spread=_round(w['centre_spread']),
                           rings=[dict(line=r['line'] - base, locus=r['locus'], centre=[_round(r['centre'][0]), _round(r['centre'][1])], radius=_round(r['radius']), residual=_round(r['residual'], 3),
                                       arc_deg=_round(r['arc_deg'], 1), n=r['n'], units=[pg['_unit_id'][(a, b)] for a, b in r['tokens'] if (a, b) in pg['_unit_id']]) for r in w['rings']],
                           labels=[pg['_unit_id'][(a, b)] for l, a, b in w.get('labels', []) if (a, b) in pg['_unit_id']]))
        wheels[folio] = dict(H=rec['H'], frame=rec.get('frame', 'recorded'), wheels=ws, rejected=[dict(line=r['line'] - base, locus=r['locus'], reason=r['reason']) for r in rec['rejected']])
    write_json(dict(version=prod['version'], frame='recorded', warp='recorded', parameters=prod['parameters'], summary={k: v for k, v in prod['summary'].items() if k != 'wheels_per_page'},
                    fields=dict(pages='{folio: {H, frame, wheels: [{id, centre, radius, centre_spread, rings: [{line (page line index), locus, centre, radius, residual, arc_deg, n, units (unit ids)}], labels (unit ids of nearby non-paragraph units)}], rejected: [{line, locus, reason}]}}',
                                display='a centred composite translates every wheel to a common centre and changes nothing else; it is a display transform (frame "display"), not measured geometry'),
                    pages=wheels), out / 'compare' / 'wheels.json.gz')
    # orders
    write_json(C.orders(ms), out / 'compare' / 'orders.json')
    # rankings for the default pool
    rank_entry = None
    if scan:
        rows_fields = ['dice_current', 'js_joined', 'spatial', 'x_dice', 'dice_recorded', 'edit_all', 'js_word']
        ranked = C.rank_pairs(data, 'all', 1, 'pages', 'both', log=log)
        per_page = {}
        for pos, r in enumerate(ranked['rows']):
            for me, other in ((r['a'], r['b']), (r['b'], r['a'])):
                lst = per_page.setdefault(me, [])
                if len(lst) < top:
                    lst.append([other, pos + 1, r['overlap_rank'], r['js_rank']] + [_round(r[k], 6) for k in rows_fields])
        bif = {}
        for face in ('inner', 'outer', 'both'):
            rk = C.rank_pairs(data, 'all', 1, face, 'both')
            bif[face] = dict(sheets=rk['sheets'], rows=rk['n_rows'], slots=rk['slots'],
                             top=[[r['a'], r['b'], pos + 1, r['overlap_rank'], r['js_rank'], _round(r.get('weakest_overlap'), 6)] + [_round(r[k], 6) for k in rows_fields] for pos, r in enumerate(rk['rows'][:top])])
        write_json(dict(version=COMPARE_VERSION, cutoff=1, pool='all', metric='both', scan=dict(pages_scanned=ranked['pages_scanned'], eligible_pages=ranked['eligible_pages'], eligible_pairs=ranked['eligible_pairs']),
                        fields=dict(pages='{folio: [[other folio, combined position (1 = best of the whole pool), overlap rank, js rank] + values]} top %d per page by the combined rank' % top,
                                    values=rows_fields, bifolia='{face: {sheets, rows, slots, top: [[a, b, position, overlap rank, js rank, weakest overlap] + values]}}',
                                    combined='the combined rank minimises the worse of the Dice rank (dice_current, descending) and the JS rank (js_joined, ascending), then their sum; ranks are competition ranks within the whole pool',
                                    scope='first paragraph line of every page with a horizontal, located opening; pairs where both lines are complete with at least two scored boxes'),
                        note=ranked['note'], pages=per_page, bifolia=bif, top=[[r['a'], r['b'], r['overlap_rank'], r['js_rank']] + [_round(r[k], 6) for k in rows_fields] for r in ranked['rows'][:top]]),
                   out / 'compare' / 'rankings.json.gz')
        rank_entry = 'compare/rankings.json.gz'
    entry = dict(pages='compare/pages.json.gz', wheels='compare/wheels.json.gz', orders='compare/orders.json', rankings=rank_entry, version=COMPARE_VERSION, bundle=bundle_key,
                 baseline=baseline, policy=app.get('policy'), math='../js/compare_math.js')
    index_path = out / 'index.json'
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding='utf-8'))
        idx['compare'] = entry
        index_path.write_text(json.dumps(idx, indent=1) + '\n', encoding='utf-8')
    if log:
        size = sum((out / 'compare' / f).stat().st_size for f in ('pages.json.gz', 'wheels.json.gz', 'orders.json') + (('rankings.json.gz',) if rank_entry else ()))
        log('wrote %s (%.2f MB gzipped): %d pages, %d units, %d wheels%s' % (out / 'compare', size / 2 ** 20, len(pages), sum(len(p['units']) for p in pages.values()), prod['summary']['wheels'],
                                                                             ', rankings for %d pairs' % ranked['eligible_pairs'] if rank_entry else ''))
    return entry


def control_label(kind, name):
    prose = 'Natural text %s, lines filled to the character budget, typeset' % name
    return {'stream': 'Generator stream %s, typeset' % name, 'markov': 'Markov word-bigram chain, %s, typeset' % (name or 'whole manuscript'),
            'prose': prose, 'prose_line': prose, 'prose_native': 'Natural text %s in its own printed lines, typeset' % name,
            'markov_box': 'DIAGNOSTIC: Markov chain %s, words swapped into the recorded boxes' % (name or 'whole manuscript'),
            'prose_box': 'DIAGNOSTIC: natural text %s, words swapped into the recorded boxes' % name}.get(kind, '%s %s' % (kind, name))
