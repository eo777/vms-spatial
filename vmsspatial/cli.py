"""Command line of the toolkit: python -m vmsspatial <command> (or `vmsspatial` once installed).

    fetch-data | verify-data          the data folder (see datafiles.py)
    info                              what is loaded: manuscript, bundle, data presence
    score                             per-token pool measures and outcomes to CSV, for any pool shape and bundle
    contrast                          the within-bifolium contrasts (raw, inside word length, inside length x pool size)
    shuffle-check                     typesetting of the layout-preserving rearrangements, with page renders
    control                           build a control text as a bundle (generator stream, Markov chain, natural prose)
    viewer-data                       data for the viewer (viewer/data)
    audit summary|flagged|token|page|check   the alignment review: counts, flagged words, one word, one page, invariants
    fetch-images                      page images (Beinecke scans or Voynichese display images) into the image cache
    ink-measure                       measure the words' ink on the page images (the ink_measures data product)
    build-products                    rebuild the shipped products from the review: manuscript bundle, registrations, baselines table, page warp, wheels (docs/DATA_MODEL.md)
    orientation                       the orientation counts of a bundle (lines by kind, pages by kind)
    audit coverage                    the coverage table per page and locus type (coverage_by_page.csv)
    realign                           align the ZL tokens to the rectangles, word by word (vmsspatial.realign; needs the XML inputs)
    plot                              print a page, a comparison overlay, a wheel or a bifolium face to a PNG (vmsspatial.plot; matplotlib)
    compare                           the overlay scores of two pages' blocks, or the ranked pairs (vmsspatial.compare)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from . import paths


def parse_spec(text):
    from .selector import PoolSpec, STUDY_SELECTOR
    if not text:
        return STUDY_SELECTOR
    kw = {}
    for part in text.split(','):
        k, _, v = part.partition('=')
        k = k.strip()
        v = v.strip()
        if k in ('direction', 'weight', 'metric', 'name'):
            kw[k] = v
        elif k == 'cap':
            kw[k] = int(v)
        else:
            kw[k] = float(v)
    return PoolSpec(**kw)


def load_any_bundle(path, policy):
    from .bundle import load_bundle, read_json
    return read_json(path) if path else load_bundle(policy)


def cmd_info(args):
    from .manuscript import Manuscript
    from .datafiles import verify
    ms = Manuscript.load(args.order)
    print(json.dumps(ms.summary(), indent=1))
    v = verify()
    print('data: %d files present and verified, %d missing, %d with a different SHA-256, %d optional files not present' % (len(v['ok']), len(v['missing']), len(v['bad']), len(v['optional_missing'])))
    if v['missing']:
        print('  missing: ' + ', '.join(v['missing'][:8]) + (' ...' if len(v['missing']) > 8 else ''))
    print('data folder: %s' % paths.data_dir())
    return 0


def cmd_score(args):
    from .manuscript import Manuscript
    from .selector import SpatialContext
    from .measures import Features, score
    from .outcomes import outcomes, token_meta
    spec = parse_spec(args.spec)
    bundle = load_any_bundle(args.bundle, args.policy)
    ctx = SpatialContext(bundle, policy=args.policy)
    tab = score(ctx, spec, Features(bundle), progress=(lambda k, n: print('  %d / %d' % (k, n), file=sys.stderr)) if args.verbose else None)
    out = outcomes(bundle['words'])
    rows = []
    line_meta = {}
    for L in bundle['lines']:
        for i in range(L['start'], L['end']):
            line_meta[i] = (L['page'], L['locus'], L.get('bifolium', ''))
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['token', 'page', 'locus', 'bifolium', 'word', 'x0', 'y0', 'x1', 'y1', 'pool_n', 'available', 'ess', 'pair_ess', 'components', 'h1', 'h2', 'worddiv', 'js', 'app_impact', 'arrival', 'repeat'])
        for i in range(ctx.n):
            b = bundle['geometry'][i] or [''] * 4
            page, locus, bif = line_meta[i]
            w.writerow([i, page, locus, bif, bundle['words'][i], *b, int(tab['n'][i]), int(tab['available'][i]), '%.4f' % tab['ess'][i], '%.4f' % tab['pair_ess'][i]]
                       + ['%.6f' % tab[k][i] if np.isfinite(tab[k][i]) else '' for k in ('components', 'h1', 'h2', 'worddiv', 'js')]
                       + ['%.5f' % out['app_impact'][i] if np.isfinite(out['app_impact'][i]) else '', '%.5f' % out['arrival'][i], int(out['repeat'][i])])
    print('wrote %s: %d tokens, %d scored (%s)' % (args.out, ctx.n, int(np.isfinite(tab['components']).sum()), spec.label()))
    return 0


def cmd_contrast(args):
    from .bundle import manuscript_of
    from .selector import SpatialContext, LINES_ABOVE_ONLY
    from .measures import Features, score
    from .outcomes import outcomes, token_meta
    from .stats import standard_contrasts, format_contrasts
    spec = parse_spec(args.spec)
    bundle = load_any_bundle(args.bundle, args.policy)
    ms = manuscript_of(bundle)
    line_words = [bundle['words'][L['start']:L['end']] for L in bundle['lines']]
    ctx = SpatialContext(bundle, policy=args.policy)
    feat = Features(bundle)
    tab = score(ctx, spec, feat)
    above = score(ctx, LINES_ABOVE_ONLY, feat) if args.cohorts else None
    node, group, bstart, bend = token_meta(ms, line_words)
    out = outcomes(bundle['words'], bstart, bend)
    res = standard_contrasts(tab, out, node, bundle['words'], out['full'], outcome=args.outcome, line_words=line_words if args.cohorts else None,
                             above_table=above, reps=args.reps)
    d = ctx.describe()
    print('Within-bifolium quintile contrast of %s (lowest minus highest fifth of the measure); %s' % (args.outcome, spec.label()))
    print('geometry %s, policy %s, %d of %d tokens located' % (d['geometry_kind'], d['policy'], d['located'], d['tokens']))
    print(format_contrasts(res))
    if args.out:
        Path(args.out).write_text(json.dumps(dict(spec=spec.as_dict(), outcome=args.outcome, context=d, results=res), indent=1, default=float), encoding='utf-8')
    return 0


def cmd_shuffle_check(args):
    from .manuscript import Manuscript
    from .bundle import load_bundle
    from .geometry import line_frames
    from .shuffles import variants, shuffled_in_boxes
    from .layout_check import check, letter_size_change, render_pages
    from .manuscript import tokenize, STUDY
    ms = Manuscript.load(**STUDY)                       # the layout check is a study of the paragraph text in its recorded frames
    app = load_bundle(args.policy, warp='recorded', **STUDY)
    frames = line_frames(app, ms)
    ms_lines = ms.line_words()
    ntok = ms.n_tokens
    V = variants(ms, frames, seed=args.seed)
    rows = {}
    rows['manuscript (recorded boxes)'] = check(ms, frames, ms_lines, app['geometry'])
    tok = tokenize(ms)
    old = shuffled_in_boxes(ms, np.cumsum(tok['since_par'] == 0), np.random.default_rng(args.seed))
    r = check(ms, frames, old, app['geometry'])
    r['moved'] = sum(a != b for A, B in zip(old, ms_lines) for a, b in zip(A, B)) / ntok
    rows['OLD: words shuffled in paragraphs, recorded boxes kept'] = r
    for name, v in V.items():
        moved = None if v['moved'] is None else (v['moved'] / len(ms.lines) if 'lines shuffled' in name else v['moved'] / ntok)
        rows[name] = check(ms, frames, v['lines'], v['geometry'], v['carried'], moved)
        rows[name]['letter_size'] = letter_size_change(v['cw_ratio'])
    print('%-62s %8s %7s %9s %7s  %s' % ('variant', 'carried', 'no box', 'overlaps', 'moved', 'box width / word width: median |log|, share off by 1.5x'))
    for name, r in rows.items():
        mv = '%6.1f%%' % (100 * r['moved']) if r['moved'] is not None else '     -'
        print('%-62s %8d %7d %9d %7s  %.3f, %.1f%% (of %d boxed words)' % (name, r['carried'], r['no_box'], r['overlaps'], mv, r['width']['median_abslog'], 100 * r['width']['off_1p5'], r['width']['boxed']))
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / 'shuffle_layout_check.json').write_text(json.dumps(rows, indent=1, default=float), encoding='utf-8')
        panels = [('manuscript (recorded boxes)', ms_lines, app['geometry'])] + [(n, v['lines'], v['geometry']) for n, v in V.items()]
        for folio in args.pages.split(','):
            render_pages(ms, frames, panels, folio, out / ('layout_check_%s.png' % folio))
            print('wrote layout_check_%s.png' % folio)
    return 0


def cmd_control(args):
    from .manuscript import Manuscript
    from .bundle import load_bundle, make_bundle, rounded_geometry, save_bundle
    from .controls import build_control
    from .manuscript import STUDY
    ms = Manuscript.load(**STUDY)                       # controls are typeset into the paragraph text's recorded line frames
    app = load_bundle('sensitivity', warp='recorded', **STUDY)
    kind, _, name = args.kind.partition(':')
    lines, geometry, comp, info = build_control(ms, app, kind, name or None, seed=args.seed, start=args.start)
    b = make_bundle(ms, lines, rounded_geometry(geometry), comp, provenance=app['geometry_provenance'], palette=app.get('palette'),
                    geometry_kind=info['geometry_kind'], passage={k: v for k, v in info.items() if k != 'geometry_kind'})
    save_bundle(b, args.out)
    print('wrote %s: %d tokens, %d boxed, components %s, geometry %s%s' % (args.out, len(b['words']), sum(1 for g in b['geometry'] if g), b['component_mode'],
                                                                            info['geometry_kind'], (', start %d' % info['start']) if info.get('start') is not None else ''))
    if info.get('typesetting'):
        t = info['typesetting']
        print('typesetting check: %.2f%% of words in a box off by more than 1.5x (guard 1%%), %d without box, %d overlaps' % (100 * t['off_1p5'], t['no_box'], t['overlaps']))
    if info.get('caveat'):
        print('CAVEAT: ' + info['caveat'])
    return 0


def cmd_viewer_data(args):
    from .viewer_data import build
    index = build(args.out, args.control, args.order, args.policy, extra=not args.no_extra, warp=args.warp, compare=not args.no_compare, line_stats=not args.no_line_stats)
    print(json.dumps(index, indent=1))
    return 0


def cmd_audit(args):
    from .audit import review as R
    review = R.load_review(args.review)
    if args.what == 'coverage':
        from .audit.coverage import coverage, totals, write_coverage
        rows = coverage(review)
        out = args.out or (paths.data_dir() / 'manuscript' / 'coverage_by_page.csv')
        write_coverage(rows, out)
        print('wrote %s: %d rows' % (out, len(rows)))
        print(json.dumps({k: v for k, v in totals(rows).items() if k != 'by_type'}, indent=1))
        return 0
    if args.what == 'summary':
        print(json.dumps(R.metrics(review), indent=1))
    elif args.what == 'flagged':
        rows = R.flagged_tokens(review, args.flags.split(',') if args.flags else None, args.pages.split(',') if args.pages else None)
        if args.out:
            R.write_csv(rows, args.out)
            print('wrote %s: %d flagged tokens' % (args.out, len(rows)))
        else:
            for r in rows[:args.limit]:
                print('%-18s %-10s %-12s %s' % (r['id'], r['text'] + r['after'], r['xml_words'], r['flags']))
            print('%d flagged tokens%s' % (len(rows), ' (first %d shown)' % args.limit if len(rows) > args.limit else ''))
    elif args.what == 'token':
        print(json.dumps(R.describe_token(review, args.id), indent=1))
    elif args.what == 'page':
        print(json.dumps(R.page_summary(review)[args.id], indent=1))
    elif args.what == 'check':
        from .audit.checks import check_review, check_bundle, all_ok
        from .bundle import load_bundle
        rep = check_review(review)
        rep.update(check_bundle(load_bundle('strict'), review))
        for k, v in rep.items():
            print('%-50s %s %s' % (k, 'ok' if v.get('ok') else 'FAIL', {kk: vv for kk, vv in v.items() if kk != 'ok'} or ''))
        return 0 if all_ok(rep) else 1
    return 0


def cmd_build_products(args):
    """The manuscript bundle from the review, registrations.json.gz from the cache, the baselines table, the page warp
    and the wheels from the sensitivity bundle; the manifest entries updated."""
    from .manuscript import Manuscript
    from .bundle import load_bundle, write_manuscript
    from .datafiles import register
    from .images import build_registration_product, PRODUCT_KEY as REG_KEY
    from .baselines import build_table, TABLE_KEY
    from .warp import build as build_warp, PRODUCT_KEY as WARP_KEY
    from .wheels import build as build_wheels, PRODUCT_KEY as WHEELS_KEY
    what = set(args.what or ['bundle', 'registrations', 'baselines', 'warp', 'wheels'])
    if 'bundle' in what:
        write_manuscript()
        register('manuscript/spatial_review.json.gz', 'The alignment review of all 39,026 ZL tokens: assignment groups with the original and display rectangles, flags, and the strict / sensitivity eligibility.')
        register('manuscript/words.json.gz', 'The manuscript bundle: every page and locus by bifolium, strict geometry in the recorded warp state, with the review block.')
    ms = Manuscript.load()                                             # the default shape: every page and locus, by bifolium
    app = load_bundle('sensitivity', warp='recorded')
    ink = None
    try:
        from .ink import load_ink
        ink = load_ink()
    except Exception as err:
        print('ink product not available (%s): the baselines table gets no ink method and the page warp uses the glyph baseline' % err)
    if 'registrations' in what:
        build_registration_product()
        register(REG_KEY, 'Registration of the recorded frame to the page images (vmsspatial.images): per page and source the matrix, residual field, per-line shifts and quality. Numbers only.')
    if 'baselines' in what:
        build_table(app, ms, ink=ink)
        register(TABLE_KEY, 'Baseline points per token under the four methods (bottom, centre, glyph, ink), recorded warp state, with the words and geometry digests of the sensitivity bundle (vmsspatial.baselines.build_table).')
    if 'warp' in what:
        build_warp(app, ms, ink=ink)
        register(WARP_KEY, "The page warp (vmsspatial.warp): per page the fitted shared warp field, per-line leave-one-out coefficients, tilt line, the baseline it was fitted on and the quality; apply with warp.apply / warp.transform / load_bundle(warp='flat').")
    if 'wheels' in what:
        build_wheels(app, ms)
        register(WHEELS_KEY, 'The wheels of the circular text (vmsspatial.wheels): per page the accepted wheels (centre, radius, rings with their fits and member tokens, nearby labels) and the rejected circular loci with reasons; recorded frame and warp state (fRos detected).')
    return 0


def cmd_orientation(args):
    from .bundle import load_bundle
    from .orientation import summary
    app = load_bundle(args.policy, pages='paragraph' if args.no_extra else 'all')
    print(json.dumps(summary(app), indent=1))
    return 0


def cmd_realign(args):
    from .realign import realign_pages, check_groups
    from .bundle import write_json
    review, _ = realign_pages(args.pages.split(',') if args.pages else None, review_path=args.review, workers=args.workers, checkpoint=args.checkpoint)
    m = review['metrics']
    print('%d tokens, located strict %d, sensitivity %d' % (m['canonical_tokens'], m['strict_eligible'], m['sensitivity_eligible']))
    for line in check_groups(review)[:20]:
        print('  ' + line)
    if args.out:
        write_json(review, args.out)
        print('wrote %s (version %s)' % (args.out, review['version']))
    return 0


def cmd_compare(args):
    from . import compare as C
    data = C.load(baseline=args.baseline)
    cutoff = 'all' if args.cutoff == 'all' else int(args.cutoff)
    if args.rank:
        r = C.rank_pairs(data, args.a if args.a in ('all', 'herbal_a', 'same', 'different', 'sheet') else 'all', cutoff if cutoff != 'all' else 1, args.scope, args.metric,
                         containing=None if args.a in ('all', 'herbal_a', 'same', 'different', 'sheet') else args.a)
        rows = C.compact_rows(r['rows'], args.top)
        print('%d pairs in the pool (%d pages scanned, %d eligible pairs%s); the %d best by %s:' % (r['n_rows'], r['pages_scanned'], r['eligible_pairs'], ', %d sheets' % r['sheets'] if r['sheets'] else '', len(rows), args.metric))
        for k, x in enumerate(rows):
            print('%3d  %-10s %-10s dice %.3f  js %.3f  spatial %.3f  ranks %s / %s' % (k + 1, x['a'], x['b'], x['dice_current'], x['js_joined'], x['spatial'] if x['spatial'] is not None else float('nan'), x['overlap_rank'], x['js_rank']))
        out = dict(r, rows=rows)
    elif args.face:
        res = C.compare_sheets(data, args.a, args.b, args.face, cutoff, args.coordinates, args.align, args.scale)
        for row in res['rows']:
            print('%-3s %-6s %-6s %s' % (row['slot'], row['pages'][0], row['pages'][1], {k: (round(v, 4) if isinstance(v, float) else v) for k, v in (row['result'] or {}).items()}))
        print('joint:', json.dumps(res['joint']))
        out = dict(rows=[dict(slot=r['slot'], pages=r['pages'], result=r['result']) for r in res['rows']], joint=res['joint'])
    else:
        if not args.b:
            raise SystemExit('name page B')
        a = C.select(data, args.a, args.block_a, cutoff, args.coordinates, args.align, args.scale)
        b = C.select(data, args.b, args.block_b, cutoff, args.coordinates, args.align, args.scale)
        out = dict(a=dict(folio=args.a, block=a['block']['key'], complete=a['complete'], located=a['located'], expected=a['expected']), b=dict(folio=args.b, block=b['block']['key'], complete=b['complete'], located=b['located'], expected=b['expected']),
                   coordinates=args.coordinates, alignment=args.align, scale=args.scale, cutoff=cutoff, frame=a['frame'], warp=a['warp'], result=C.measure(a, b), per_line=C.per_line(a, b) if cutoff != 'all' else None)
        if args.details:
            out['details'] = C.details(a, b)
        print(json.dumps({k: v for k, v in out.items() if k != 'details'}, indent=1))
        if args.details:
            for c in out['details']['connected']:
                print('  %-30s | %-30s  similarity %.3f edits %d%s' % (c['text_a'], c['text_b'], c['similarity'], c['edits'], '' if c['clean'] else '  (flagged)'))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding='utf-8')
        print('wrote %s' % args.out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='vmsspatial', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('fetch-data', help='download or copy the data files')
    p.add_argument('--from-workspace', action='store_true')
    p.add_argument('--group', action='append')
    p.add_argument('--force', action='store_true')
    p.add_argument('--out')
    p.add_argument('--optional', action='store_true', help='include every optional file (raw inputs, study files, scans)')
    sub.add_parser('verify-data', help='check every present data file against the manifest')
    p = sub.add_parser('info')
    p.add_argument('--order', default=None, help='bifolia (default) | folio | path1')
    for name, fn in (('score', cmd_score), ('contrast', cmd_contrast)):
        p = sub.add_parser(name)
        p.add_argument('--spec', help='pool shape, e.g. "left=3,depth=8,angle=45,weight=distance" (default: the study selector)')
        p.add_argument('--bundle', help='a bundle file (default: the manuscript)')
        p.add_argument('--policy', default='strict', help='strict | sensitivity')
        p.add_argument('--out', default='scores.csv' if name == 'score' else None)
        p.add_argument('--verbose', action='store_true')
        if name == 'contrast':
            p.add_argument('--outcome', default='app_impact', help='app_impact | arrival | repeat | departure')
            p.add_argument('--reps', type=int, default=1000)
            p.add_argument('--cohorts', action='store_true', help='also the interior cohorts A (study pool >= 15) and B (lines-above pool >= 15)')
    p = sub.add_parser('shuffle-check')
    p.add_argument('--policy', default='sensitivity')
    p.add_argument('--seed', type=int, default=1028)
    p.add_argument('--pages', default='f75r,f33v')
    p.add_argument('--out')
    p = sub.add_parser('control')
    p.add_argument('kind', help='stream:<key> | markov:<whole|currier|section> | prose:<text> | prose_native:<text>, every one typeset into the line frames; markov_box / prose_box swap words into the recorded boxes and are diagnostics only')
    p.add_argument('--seed', type=int)
    p.add_argument('--start', type=int, help='passage start of a prose text (recorded in the bundle; drawn from --seed otherwise)')
    p.add_argument('--out', required=True)
    p = sub.add_parser('viewer-data')
    p.add_argument('--no-extra', action='store_true', help='leave out the labels, circular pages and the Rosettes (the 207 study pages\' paragraph text only)')
    p.add_argument('--out')
    p.add_argument('--control', action='append', help='kind:name (repeatable), as for `control`')
    p.add_argument('--order', default='bifolia', help='bifolia (default: the sheets, each kept together) | folio (the page sequence) | path1')
    p.add_argument('--policy', default='strict')
    p.add_argument('--warp', default='flat', choices=('flat', 'recorded'), help='the state the measures are computed in (boxes are always drawn recorded)')
    p.add_argument('--no-compare', action='store_true', help='leave out the comparison extras (viewer/data/compare: units, anchors, blocks, breaks, wheels, orders, pair rankings)')
    p.add_argument('--no-line-stats', action='store_true', help='leave the line, baseline and warp measures out of the manuscript bundle')
    p = sub.add_parser('audit')
    p.add_argument('what', choices=['summary', 'flagged', 'token', 'page', 'check', 'coverage'])
    p.add_argument('id', nargs='?')
    p.add_argument('--review')
    p.add_argument('--flags')
    p.add_argument('--pages')
    p.add_argument('--out')
    p.add_argument('--limit', type=int, default=40)
    p = sub.add_parser('fetch-images', help='download page images into the cache (VMS_SPATIAL_IMAGES or %%LOCALAPPDATA%%/vmsspatial/images)')
    p.add_argument('--source', default='beinecke', choices=('beinecke', 'display'))
    p.add_argument('--folios', help='comma-separated folios (default: every mapped page)')
    p.add_argument('--build-index', action='store_true', help='rebuild resources/beinecke_iiif.json from the Yale manifest first')
    p = sub.add_parser('build-products', help='rebuild the shipped products from the review (manuscript bundle, registrations, baselines table, page warp, wheels) and their manifest entries')
    p.add_argument('what', nargs='*', choices=['bundle', 'registrations', 'baselines', 'warp', 'wheels'], help='default: all five')
    p = sub.add_parser('orientation', help='orientation counts of the manuscript bundle')
    p.add_argument('--policy', default='sensitivity')
    p.add_argument('--no-extra', action='store_true')
    p = sub.add_parser('realign', help='align the ZL tokens to the rectangles word by word (default: every page); --out writes the new review file')
    p.add_argument('--pages', help='comma-separated folios')
    p.add_argument('--review', help='the review to start from (default: the shipped one)')
    p.add_argument('--workers', type=int, default=1, help='worker processes (default 1)')
    p.add_argument('--checkpoint', help="a folder for each page's result as it finishes; a rerun skips the pages already there")
    p.add_argument('--out')
    p = sub.add_parser('ink-measure', help='measure the ink of every word on the page images and write the data product')
    p.add_argument('--source', default='beinecke', choices=('beinecke', 'display'))
    p.add_argument('--folios', help='comma-separated folios (default: every page of the bundle)')
    p.add_argument('--out', help='output file (default: <data>/manuscript/ink_measures.json.gz)')
    p.add_argument('--policy', default='sensitivity')
    p = sub.add_parser('plot', help='print a page (default), a comparison (--compare FOLIO), a wheel (--wheel), centred wheels (--centered) or a bifolium face (--bifolium) to --out', add_help=False)
    p = sub.add_parser('compare', help='overlay scores of two pages, or the ranked pairs (--rank)')
    p.add_argument('a', help="page A ('f20v'), or a bifolium id with --face")
    p.add_argument('b', nargs='?', help='page B (or bifolium B)')
    p.add_argument('--block-a', default='opening')
    p.add_argument('--block-b', default='opening')
    p.add_argument('--cutoff', default='all', help='1..5 or all')
    p.add_argument('--coordinates', default='flat', choices=('flat', 'recorded'))
    p.add_argument('--align', default='starts', choices=('starts', 'page'))
    p.add_argument('--scale', default='pixels', choices=('pixels', 'body_height'))
    p.add_argument('--face', choices=('inner', 'outer', 'both'), help='compare two bifolia slot by slot on this face')
    p.add_argument('--rank', action='store_true', help='the ranked pairs of the first-line scan instead (a = pool: all | herbal_a | same | different | sheet)')
    p.add_argument('--scope', default='pages', choices=('pages', 'inner', 'outer', 'both'))
    p.add_argument('--metric', default='both')
    p.add_argument('--top', type=int, default=25)
    p.add_argument('--baseline', default='auto')
    p.add_argument('--details', action='store_true', help='also the word-segment correspondences')
    p.add_argument('--out', help='write the result as JSON')
    args, rest = ap.parse_known_args(argv)
    if args.cmd == 'plot':
        from .plot import main as plot_main
        return plot_main(rest)
    if rest:
        ap.error('unrecognized arguments: %s' % ' '.join(rest))
    if args.cmd == 'compare':
        return cmd_compare(args)
    if args.cmd == 'fetch-images':
        from .images import main as images_main
        return images_main([x for x in ['--source', args.source] + (['--folios', args.folios] if args.folios else []) + (['--build-index'] if args.build_index else [])])
    if args.cmd == 'ink-measure':
        from .manuscript import Manuscript
        from .bundle import load_bundle
        from .ink import measure_pages, summary
        ms = Manuscript.load()
        prod = measure_pages(load_bundle(args.policy, warp='recorded'), ms, folios=args.folios.split(',') if args.folios else None, source=args.source, out=args.out or None)
        print(json.dumps(summary(prod, ms), indent=1))
        return 0
    if args.cmd == 'fetch-data':
        from .datafiles import main as fetch_main
        return fetch_main([a for a in (['--from-workspace'] if args.from_workspace else []) + [x for g in (args.group or []) for x in ('--group', g)] + (['--optional'] if args.optional else []) + (['--force'] if args.force else []) + (['--out', args.out] if args.out else [])])
    if args.cmd == 'verify-data':
        from .datafiles import verify
        v = verify()
        print('%d ok, %d missing, %d bad, %d optional files not present' % (len(v['ok']), len(v['missing']), len(v['bad']), len(v['optional_missing'])))
        for k in v['bad']:
            print('  bad: ' + k)
        for k in v['missing']:
            print('  missing: ' + k)
        return 1 if v['bad'] or v['missing'] else 0
    fn = dict(info=cmd_info, score=cmd_score, contrast=cmd_contrast, **{'shuffle-check': cmd_shuffle_check, 'viewer-data': cmd_viewer_data, 'build-products': cmd_build_products},
              control=cmd_control, audit=cmd_audit, orientation=cmd_orientation, realign=cmd_realign).get(args.cmd)
    if fn is None:
        ap.print_help()
        return 1
    return fn(args)


if __name__ == '__main__':
    sys.exit(main())
