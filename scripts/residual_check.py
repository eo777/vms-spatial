"""Residual association under the joint control against a GEOMETRY-MATCHED shuffle baseline.

The observation and its shuffles are scored in the same geometry: with --geometry recorded (default) the manuscript's
reviewed rectangles are kept, and the size-matched paragraph shuffles keep them too (a same-length word takes the
slot's box); with --geometry synthetic the manuscript is re-typeset into its own line frames and so is every shuffle.
Reported per cohort (all / interior A / interior B), measure (components, H2, word diversity) and control (raw, inside
length, inside length x pool size): the observed value, the shuffle mean and range, the rank, the one-sided permutation
probability and the excess over the baseline. Any bundle can be scored the same way with --bundle, each against its own
baseline, which is how texts are to be compared.

    python scripts/residual_check.py --shuffles 30                        # about ten minutes
    python scripts/residual_check.py --geometry synthetic --shuffles 19
    python scripts/residual_check.py --bundle my_control.json.gz --shuffles 30
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial import Manuscript, load_bundle, SpatialContext, STUDY_SELECTOR
from vmsspatial.selector import LINES_ABOVE_ONLY
from vmsspatial.cli import parse_spec
from vmsspatial.measures import Features, score
from vmsspatial.outcomes import outcomes, token_meta
from vmsspatial.stats import standard_contrasts, format_contrasts, baseline_summary, format_baseline
from vmsspatial.geometry import line_frames, synthetic_geometry
from vmsspatial.bundle import make_bundle, read_json
from vmsspatial.shuffles import baseline


def analyse(ms, bundle, spec, reps=0):
    ctx = SpatialContext(bundle)
    feat = Features(bundle)
    tab = score(ctx, spec, feat)
    above = score(ctx, LINES_ABOVE_ONLY, feat)
    line_words = [bundle['words'][L['start']:L['end']] for L in bundle['lines']]
    node, group, bstart, bend = token_meta(ms, line_words)
    out = outcomes(bundle['words'], bstart, bend)
    return standard_contrasts(tab, out, node, bundle['words'], out['full'], line_words=line_words, above_table=above, reps=reps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shuffles', type=int, default=30)
    ap.add_argument('--unit', default='paragraph', help='paragraph | page | bifolium | all')
    ap.add_argument('--geometry', default='recorded', help='recorded | synthetic (the manuscript); a --bundle brings its own geometry_kind')
    ap.add_argument('--bundle', help='score another bundle (a control) against its own baseline')
    ap.add_argument('--spec')
    ap.add_argument('--out')
    args = ap.parse_args()
    spec = parse_spec(args.spec) if args.spec else STUDY_SELECTOR
    ms = Manuscript.load(**STUDY)
    frames = line_frames(load_bundle('sensitivity', warp='recorded', **STUDY), ms)
    if args.bundle:
        bundle = read_json(args.bundle)
        kind = bundle.get('geometry_kind')
        if kind not in ('recorded', 'flattened', 'synthetic'):
            raise SystemExit('the bundle has no geometry_kind; rebuild it with make_bundle(..., geometry_kind=...)')
    elif args.geometry == 'recorded':
        bundle, kind = load_bundle('strict', warp='recorded', **STUDY), 'recorded'
    else:
        lines = ms.line_words()
        bundle, kind = make_bundle(ms, lines, synthetic_geometry(lines, frames, ms), 'zattera', geometry_kind='synthetic'), 'synthetic'
    comp = 'letters' if bundle['component_mode'].startswith('letters') else 'zattera'
    line_words = [bundle['words'][L['start']:L['end']] for L in bundle['lines']]
    observed = analyse(ms, bundle, spec, reps=500)
    print(format_contrasts(observed, 'observed (%s geometry): %s' % (kind, spec.label())))
    shuffles = []
    for k, (sl, sg) in enumerate(baseline(ms, line_words, bundle['geometry'], kind, frames=frames, k=args.shuffles, unit=args.unit)):
        shuffles.append(analyse(ms, make_bundle(ms, sl, sg, comp, geometry_kind=kind), spec))
        print('  shuffle %d/%d done' % (k + 1, args.shuffles), file=sys.stderr, flush=True)
    summary = baseline_summary(observed, shuffles)
    print(format_baseline(summary, '%d size-matched %s shuffles in the %s geometry: observed vs mean (min..max), excess, rank, one-sided p' % (args.shuffles, args.unit, kind)))
    if args.out:
        Path(args.out).write_text(json.dumps(dict(spec=spec.as_dict(), geometry=kind, unit=args.unit, shuffles=args.shuffles, observed=observed, summary=summary), indent=1, default=float), encoding='utf-8')


if __name__ == '__main__':
    main()
