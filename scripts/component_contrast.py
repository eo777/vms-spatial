"""The pool-diversity contrast with every control that the 28 October 2026 reviews required, in one report.

For a text laid on the page geometry: score every token's pool (the study selector, its width-neutral form and the
writing-cursor form, or any PoolSpec), then the within-bifolium quintile contrast of word impact (lowest minus highest
diversity fifth) for component diversity, H2 and word diversity, raw / inside exact word length / inside length x
pool-size tertile, on all words and on the interior cohorts. Runs on the manuscript under the reviewed geometry and
(--streams) on the saved copier streams laid into the same lines with synthetic rectangles. The geometry kind is printed with every block: do not compare across kinds.

    python scripts/component_contrast.py                 # manuscript, three selectors, about a minute
    python scripts/component_contrast.py --streams       # + three copier streams (first seed each)
    python scripts/component_contrast.py --spec "left=3,depth=8,angle=45,weight=uniform"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial import Manuscript, load_bundle, SpatialContext, STUDY_SELECTOR
from vmsspatial.selector import WIDTH_NEUTRAL_SELECTOR, CURSOR_SELECTOR, LINES_ABOVE_ONLY
from vmsspatial.cli import parse_spec
from vmsspatial.measures import Features, score
from vmsspatial.outcomes import outcomes, token_meta
from vmsspatial.stats import standard_contrasts, format_contrasts
from vmsspatial.geometry import line_frames, synthetic_geometry
from vmsspatial.bundle import make_bundle
from vmsspatial.controls import STREAMS, read_stream


def analyse(ms, bundle, specs, policy='strict', reps=500):
    ctx = SpatialContext(bundle, policy=policy)
    feat = Features(bundle)
    line_words = [bundle['words'][L['start']:L['end']] for L in bundle['lines']]
    node, group, bstart, bend = token_meta(ms, line_words)
    out = outcomes(bundle['words'], bstart, bend)
    above = score(ctx, LINES_ABOVE_ONLY, feat)
    res = {}
    for spec in specs:
        tab = score(ctx, spec, feat)
        res[spec.label()] = standard_contrasts(tab, out, node, bundle['words'], out['full'], line_words=line_words, above_table=above, reps=reps)
    return res, ctx.describe()


def show(name, res, d):
    print('\n== %s   [geometry %s, policy %s, %d/%d located]' % (name, d['geometry_kind'], d['policy'], d['located'], d['tokens']))
    for label, r in res.items():
        print(format_contrasts(r, '  -- ' + label))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', help='one pool shape instead of the three standard selectors')
    ap.add_argument('--streams', action='store_true')
    ap.add_argument('--reps', type=int, default=500)
    ap.add_argument('--out')
    args = ap.parse_args()
    specs = [parse_spec(args.spec)] if args.spec else [STUDY_SELECTOR, WIDTH_NEUTRAL_SELECTOR, CURSOR_SELECTOR]
    ms = Manuscript.load(**STUDY)
    results = {}
    print('Within-bifolium quintile contrast of word impact, lowest minus highest fifth of the pool measure.')
    strict = load_bundle('strict', warp='recorded', **STUDY)
    results['manuscript (reviewed geometry)'] = analyse(ms, strict, specs, reps=args.reps)
    show('manuscript (reviewed geometry)', *results['manuscript (reviewed geometry)'])
    if args.streams:
        frames = line_frames(load_bundle('sensitivity', warp='recorded', **STUDY), ms)
        for key in ('timm', 'timm_spatial', 'noinnov_spatial'):
            lines = read_stream(STREAMS[key][1][0])
            b = make_bundle(ms, lines, synthetic_geometry(lines, frames, ms), 'zattera', geometry_kind='synthetic')
            results[STREAMS[key][0]] = analyse(ms, b, specs, reps=min(args.reps, 200))
            show(STREAMS[key][0], *results[STREAMS[key][0]])
    if args.out:
        Path(args.out).write_text(json.dumps({k: dict(contrasts=v[0], context=v[1]) for k, v in results.items()}, indent=1, default=float), encoding='utf-8')


if __name__ == '__main__':
    main()
