"""Word bundles: the one data structure the analysis and the viewer share.

A bundle is a dict:
    schema        2 (plain) or 3 (reviewed: carries spatialReview)
    window        100
    words         [str] every token in stream order
    lines         [{page, locus, bifolium, start, end}] contiguous token ranges per line
    geometry      [[x0, y0, x1, y1] | None] per token, in the coordinate frame of the Voynichese XML pages
    components    {word: [units]} the component function applied to every distinct word
    component_mode 'zattera; lossless; within-word pairs only' or 'letters; letter pairs'
    palette       501 colours of the viewer's diversity scale (optional)
    spatialReview   the manuscript bundle only (see audit/)
    input_geometry_provenance       for bundles derived from the manuscript's geometry: which policy produced the frames
    frame, warp, source             the coordinate tags (``vmsspatial.frames``): 'recorded' / 'recorded' / 'voynichese'
                                    for the recorded rectangles; warp 'flat' once ``vmsspatial.warp`` removed the page warp
    lines[i]['locus_type'], lines[i]['orientation']   the ZL locus type and the orientation record (``vmsspatial.orientation``)

Geometry policies of the manuscript bundle (``load_bundle(policy)``):
    strict          the reviewed word-level rectangles (schema 3 default); shared or disputed assignments are None
    sensitivity     also the shared / spelling-disputed locations, as approximations

Defaults of ``load_bundle``: every page and locus (``pages='all'``), the manuscript by bifolium (``order='bifolia'``),
the flat warp state (``warp='flat'``: the page warp of the photograph removed with the shipped page warp product; pages
without a fitted field stay as recorded, ``warp.page_status``). The study shape of October 2026 is
``load_bundle(policy, pages='paragraph', order='path1', warp='recorded')``; a bundle records its `pages`, `order`,
`policy` and tags.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import warnings
from typing import Callable, Dict, List, Optional

import numpy as np

from . import paths
from .units import COMPONENT_FUNCTIONS, COMPONENT_MODES

POLICIES = ('strict', 'sensitivity')


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def read_json(path):
    path = str(path)
    if path.endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(obj, path, deterministic=True):
    data = json.dumps(obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    path = str(path)
    if path.endswith('.gz'):
        with open(path, 'wb') as f:
            f.write(gzip.compress(data, mtime=0) if deterministic else gzip.compress(data))
    else:
        with open(path, 'wb') as f:
            f.write(data)


def clean_geometry(geometry, lines):
    """The page-relative size exclusion, applied exactly once."""
    pages = {}
    for line in lines:
        pages.setdefault(line['page'], []).extend(range(line['start'], line['end']))
    result = list(geometry)
    for indices in pages.values():
        boxes = [geometry[i] for i in indices if geometry[i] is not None]
        if not boxes:
            continue
        width = np.median([b[2] - b[0] for b in boxes])
        height = np.median([b[3] - b[1] for b in boxes])
        for i in indices:
            b = geometry[i]
            if b and (b[2] - b[0] > 6 * width or b[3] - b[1] > 2.5 * height):
                result[i] = None
    return result


def load_bundle(policy='strict', path=None, pages='all', order=None, warp='flat', orientation=True, extra=None) -> dict:
    """The manuscript bundle under a geometry policy: by default every page and locus of the recorded manuscript by
    bifolium, in the flat warp state (the stored page warp applied, ``vmsspatial.warp.flatten_bundle``; a page without a
    fitted field stays as recorded, see ``warp.page_status``). `order='folio'` is the page sequence; `pages='paragraph'`
    and `order='path1'` give the study shape (``manuscript.STUDY``), `warp='recorded'` the rectangles as drawn on the photographs. The
    returned dict's ``geometry`` is the policy's, ``spatialReview`` (a schema-3 bundle) keeps its per-token mask in
    step with it, every bundle carries the frame tags (``vmsspatial.frames``), `pages`, `order` and, unless
    `orientation` is False, the orientation record of every line (``vmsspatial.orientation``). `extra` is the
    deprecated older spelling of `pages`."""
    from .manuscript import page_set, DEFAULT_ORDER, ORDERS
    if policy not in POLICIES:
        raise ValueError('policy must be one of %r' % (POLICIES,))
    if warp not in ('recorded', 'flat'):
        raise ValueError("warp must be 'recorded' or 'flat'")
    pages = page_set(pages, extra)
    order = order or DEFAULT_ORDER
    if order not in ORDERS:
        raise ValueError('order must be one of %r' % (ORDERS,))
    app = read_json(path or paths.resolve('manuscript/words.json.gz'))
    review = app.get('spatialReview')
    if policy == 'sensitivity':
        if not review:
            raise ValueError('the sensitivity policy needs a schema-3 reviewed bundle')
        geometry = review['sensitivityGeometry']
    else:
        geometry = app['geometry']
    app = dict(app, geometry=geometry, policy=policy, geometry_kind='recorded')
    if policy == 'sensitivity' and review:
        app['spatialReview'] = dict(review, tokens=[dict(t, strict=g is not None) for t, g in zip(review['tokens'], geometry)])
    app['geometry_provenance'] = dict(app.get('geometry_provenance') or {}, policy=policy, words_sha256=digest(app['words']), geometry_sha256=digest(geometry),
                                      review_version=review['version'] if review else None)
    from .frames import tag
    tag(app, frame='recorded', warp='recorded', source='voynichese')
    if pages != app['pages'] or order != app['order']:
        from .manuscript import Manuscript
        app = extend_bundle(app, policy, ms=Manuscript.load(order, pages=pages))
    if orientation:
        from .orientation import attach
        attach(app)
    if warp == 'flat':
        from .warp import flatten_bundle
        app = flatten_bundle(app)
    return app


def extend_bundle(app: dict, policy='strict', ms=None, review=None, supplement=None, extra=True) -> dict:
    """The manuscript bundle re-sequenced to the lines of a Manuscript `ms` (default: ``Manuscript.load()``, every
    page and locus by bifolium): the stream follows the manuscript's line order, every line takes the alignment
    review's boxes (strict or sensitivity assignments, by policy), and the Rosettes take the supplement's detected boxes
    whose confidence reaches its floor, in the display image's frame. The bundle records `pages`, `order`,
    `extra_pages`, `extra_lines` (those outside the study transcription), `detected_pages` and per-token
    `detected_confidence`."""
    from .manuscript import Manuscript, ORDERS, load_tokens
    from .audit.review import load_review, geometry as review_geometry, package
    ms = ms or Manuscript.load(app.get('order') if app.get('order') in ORDERS else None, pages='all' if extra else 'paragraph')
    review = review or load_review()
    if [(L['folio'], L['locus']) for L in ms.lines] == [(L['page'], L['locus']) for L in app['lines']]:
        app['pages'] = ms.page_set
        app['order'] = ms.order
        return app
    rev_geom = review_geometry(review, policy)
    by_line = {}
    for t in review['tokens']:
        by_line.setdefault((t['page'], t['locus']), []).append(t)
    sup_path = paths.resolve('manuscript/supplement_fRos.json', required=False)
    if supplement is None and sup_path and Path(sup_path).exists():
        supplement = read_json(sup_path)
    sup_tokens = (supplement or {}).get('tokens', {})
    floor = (supplement or {}).get('confidence_floor', 0.35)
    words, lines, geometry = [], [], []
    confidence, detected_pages, extra_pages, extra_lines = {}, set(), set(), 0
    study = load_tokens()['lines']
    study_lines = {(L['folio'], str(L['locus'])) for L in study}
    study_pages = {L['folio'] for L in study}
    for L in ms.lines:
        key = (L['folio'], L['locus'])
        start = len(words)
        toks = [t for t in by_line.get(key, []) if '?' not in t['text']]
        assert [t['text'] for t in toks] == L['words'], key
        if key not in study_lines:
            extra_lines += 1
            if L['folio'] not in study_pages:
                extra_pages.add(L['folio'])
        for t in toks:
            words.append(t['text'])
            box = rev_geom.get(t['id'])
            if box is None and key not in study_lines and t['id'] in sup_tokens:
                rec = sup_tokens[t['id']]
                if rec['display_box'] and rec['confidence'] >= floor:
                    box = rec['display_box']
                    confidence[len(words) - 1] = rec['confidence']
                    detected_pages.add(L['folio'])
            geometry.append(box)
        lines.append(dict(page=L['folio'], locus=L['locus'], bifolium=L['node'], start=start, end=len(words)))
    components = dict(app.get('components', {}))
    mode = app.get('component_mode', 'zattera')
    fn = COMPONENT_FUNCTIONS.get(mode.split(';')[0].strip(), COMPONENT_FUNCTIONS.get('zattera'))
    for w in words:
        if w not in components:
            components[w] = fn(w)
    out = dict(app, words=words, lines=lines, geometry=geometry, components=components,
               extra_pages=sorted(extra_pages), extra_lines=extra_lines, detected_pages=sorted(detected_pages),
               detected_confidence={str(k): v for k, v in confidence.items()}, extra=ms.extra, pages=ms.page_set, order=ms.order)
    if app.get('spatialReview'):
        block = package(review, words, lines)
        # the supplement's boxes become groups of their own, flagged 'detected', so the viewer draws and selects them
        for i, (w, b) in enumerate(zip(words, geometry)):
            if i in confidence:
                t = block['tokens'][i]
                key = 'det:' + t['id']
                block['groups'][key] = dict(id=key, page=t['page'], tokens=[t['id']], positions=[i], box=b, parts=[b], display_parts=[b], xml_indices=[],
                                            label=w, flags=['detected'], safe=True, status='detected', cost=None, xml_words=[],
                                            resolution=dict(method='detected', confidence=confidence[i]))
                t['group'] = key
                t['strict'] = t['sensitivity'] = True
                t['flags'] = list(t.get('flags', [])) + ['detected']
                block['geometry'][i] = b
                block['sensitivityGeometry'][i] = b
        if policy == 'sensitivity':
            block['tokens'] = [dict(t, strict=g is not None) for t, g in zip(block['tokens'], geometry)]
        out['spatialReview'] = block
    out['geometry_provenance'] = dict(app['geometry_provenance'], extra_pages=len(extra_pages), extra_lines=extra_lines, detected_pages=sorted(detected_pages),
                                      geometry_sha256=digest(out['geometry']), words_sha256=digest(words))
    from .frames import tag
    tag(out, frame='recorded', warp=app.get('warp') or 'recorded', source=app.get('source') or 'voynichese')
    if detected_pages:
        out['frame_image'] = {p: 'viewer/img/%s.jpg' % p for p in sorted(detected_pages)}
    out['extra'] = bool(ms.extra)
    out['pages'] = ms.page_set
    out['order'] = ms.order
    if app['lines'] and all('orientation' in L for L in app['lines']):
        from .orientation import attach
        attach(out, ms, force=True)
    return out


def write_manuscript(out=None, log=print) -> dict:
    """Rebuild the shipped manuscript bundle (``manuscript/words.json.gz``) from the alignment review: every page and
    locus by bifolium, strict geometry, recorded warp state, with the review block; the components and the palette
    carry over. Returns the bundle."""
    from .manuscript import Manuscript
    path = paths.resolve('manuscript/words.json.gz')
    base = read_json(path)
    base = {k: base[k] for k in ('schema', 'window', 'components', 'component_mode', 'palette')}
    base.update(words=[], lines=[], geometry=[], spatialReview=True, order=None, pages=None, geometry_provenance=dict(policy='strict'))
    app = extend_bundle(base, 'strict', Manuscript.load())
    app.pop('geometry_kind', None)
    target = out or (paths.data_dir() / 'manuscript' / 'words.json.gz')
    write_json(app, target)
    if log:
        log('wrote %s: %d tokens, %d located' % (target, len(app['words']), sum(1 for b in app['geometry'] if b)))
    return app


def make_bundle(ms, line_words: List[List[str]], geometry, components: str = 'zattera', provenance=None, palette=None,
                component_fn: Optional[Callable] = None, geometry_kind: Optional[str] = None, passage: Optional[dict] = None) -> dict:
    """A schema-2 bundle for any line-aligned text laid into the manuscript's lines (a generator stream, a shuffle, a
    control text). `components` names a component function ('zattera', 'raw', 'letters') or pass `component_fn`.
    `geometry_kind` says what the rectangles are, 'recorded' (the manuscript's own boxes reused one word per box),
    'flattened' (the recorded boxes with each page's photographic warp removed, ``flatten.flatten``) or
    'synthetic' (laid by character position): every spatial statistic depends on it (RESULTS section 8: the same prose
    gives +0.020 under recorded and +0.134 under length-proportional synthetic boxes), so it travels with the bundle and
    the shuffle baseline must match it. `passage` records where a control text was cut (its start offset)."""
    fn = component_fn or COMPONENT_FUNCTIONS[components]
    mode = COMPONENT_MODES.get(components, components) if component_fn is None else components
    words, lines = [], []
    for L, ws in zip(ms.lines, line_words):
        lines.append(dict(page=L['folio'], locus=L['locus'], bifolium=L['node'], start=len(words), end=len(words) + len(ws)))
        words += list(ws)
    assert len(geometry) == len(words), 'geometry and words differ in length'
    out = dict(schema=2, window=100, words=words, lines=lines, geometry=[None if b is None else [float(v) for v in b] for b in geometry],
               components={w: fn(w) for w in sorted(set(words))}, component_mode=mode,
               pages=getattr(ms, 'page_set', None), order=getattr(ms, 'order', None))
    if provenance:
        out['input_geometry_provenance'] = provenance
    if palette:
        out['palette'] = palette
    if geometry_kind is None:
        warnings.warn("make_bundle: say geometry_kind='recorded' or 'synthetic'; statistics and shuffle baselines depend on it", stacklevel=2)
    else:
        out['geometry_kind'] = geometry_kind
    if passage:
        out['passage'] = passage
    from .frames import tag
    tag(out)
    for L, M in zip(out['lines'], ms.lines):
        if M.get('locus_type'):
            L['locus_type'] = M['locus_type']
    return out


def manuscript_of(app: dict):
    """The Manuscript whose lines a bundle follows (its `pages` and `order`; the study shape for an untagged bundle)."""
    from .manuscript import Manuscript, ORDERS, PAGE_SETS
    order = app.get('order') if app.get('order') in ORDERS else 'path1'
    pages = app.get('pages') if app.get('pages') in PAGE_SETS else 'paragraph'
    return Manuscript.load(order, pages=pages)


def rounded_geometry(geometry):
    return [None if b is None else [int(round(v)) for v in b] for b in geometry]


def save_bundle(bundle: dict, path):
    write_json(bundle, path)


def validate_bundle(bundle: dict) -> dict:
    """Structural checks; returns counts. Raises AssertionError on a defect."""
    words, lines, geometry = bundle['words'], bundle['lines'], bundle['geometry']
    assert len(geometry) == len(words), 'geometry length'
    at = 0
    for L in lines:
        assert L['start'] == at and L['end'] >= L['start'], 'lines are not contiguous'
        at = L['end']
    assert at == len(words), 'lines do not cover the words'
    missing = [w for w in set(words) if w not in bundle['components']]
    assert not missing, 'components missing for %d words' % len(missing)
    for w, parts in bundle['components'].items():
        assert ''.join(parts) == w, 'components do not join back to %r' % w
    for b in geometry:
        assert b is None or (len(b) == 4 and b[2] >= b[0] and b[3] >= b[1]), 'bad box %r' % (b,)
    return dict(tokens=len(words), lines=len(lines), boxed=sum(1 for b in geometry if b is not None), pages=len({L['page'] for L in lines}))


def bundle_lines_to_line_words(bundle: dict) -> List[List[str]]:
    return [bundle['words'][L['start']:L['end']] for L in bundle['lines']]
