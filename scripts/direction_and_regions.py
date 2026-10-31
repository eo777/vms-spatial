"""Pool shapes around a word: the cone above against its mirror below, lines above only, the same line only, and a
custom region built from masks; a paired contrast for the direction test.

A copier can only copy what is already written, so copying from the page should make the cone above predict a word's
repetition better than the same cone below it; bursts of local repetition predict both alike.

    python scripts/direction_and_regions.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial import Manuscript, load_bundle, SpatialContext, PoolSpec, STUDY_SELECTOR
from vmsspatial.selector import Region
from vmsspatial.measures import Features, measure, score
from vmsspatial.outcomes import outcomes, token_meta
from vmsspatial.stats import paired_contrast, quintile_contrast


def main():
    ms = Manuscript.load(**STUDY)
    bundle = load_bundle('strict', warp='recorded', **STUDY)
    ctx = SpatialContext(bundle)
    feat = Features(bundle)
    node, group, bstart, bend = token_meta(ms, ms.line_words())
    out = outcomes(bundle['words'], bstart, bend)
    specs = {
        'study selector (above + left)': STUDY_SELECTOR,
        'mirror (below + right)': STUDY_SELECTOR.mirror(),
        'lines above only': PoolSpec(left=0, depth=8),
        'lines below only': PoolSpec(left=0, depth=8).mirror(),
        'same line, 3 to the left': PoolSpec(left=3, depth=0),
        'uniform weights': PoolSpec(weight='uniform'),
    }
    tables = {k: score(ctx, s, feat) for k, s in specs.items()}
    print('Within-bifolium quintile contrast of word impact (lowest minus highest fifth of component diversity):')
    for k, t in tables.items():
        base = out['full'] & np.isfinite(t['components'])
        r = quintile_contrast(t['components'], out['app_impact'], node, base, reps=500)
        print('  %-32s %+.3f [%+.3f,%+.3f]  cohort %d, mean pool %.1f' % (k, r['diff'], *r['ci'], base.sum(), np.nanmean(t['n'][base])))
    a, b = tables['study selector (above + left)'], tables['mirror (below + right)']
    base = out['full'] & np.isfinite(a['components']) & np.isfinite(b['components'])
    p = paired_contrast(a['components'], b['components'], out['app_impact'], node, base, reps=1000)
    print('Direction test, same tokens: above %+.3f, below %+.3f, paired difference %+.3f [%+.3f,%+.3f]' % (p['a'], p['b'], p['diff'], *p['ci']))
    # a custom region: the rectangle two lines up to one line down, within four word widths, weighted by distance
    def rect_pool(i):
        c = ctx.candidates(i, 'all')
        if c is None:
            return None
        return ctx.select(i, Region.rect(c, -4, -1.5, 4, 2.5) & ~Region.same_line(c), Region.distance_weights(c), cap=100, candidates=c)
    vals = np.full(ctx.n, np.nan)
    for i in range(ctx.n):
        p = rect_pool(i)
        if p is not None and p.n:
            vals[i] = measure(feat, p)['components']
    base = out['full'] & np.isfinite(vals)
    r = quintile_contrast(vals, out['app_impact'], node, base, reps=500)
    print('Custom rectangle (4 word widths, 2 lines up to 1 line down, other lines only): %+.3f [%+.3f,%+.3f]' % (r['diff'], *r['ci']))


if __name__ == '__main__':
    main()
