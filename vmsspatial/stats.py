"""The statistics of the spatial studies: within-bifolium quintile contrasts, stratified contrasts, held-out fits.

    quintile_contrast   inside each bifolium, tokens are split into fifths of a pool measure; the outcome's mean in the
                        lowest fifth minus the highest, pooled over bifolia (counts added, then divided); bootstrap over
                        bifolia for the interval. "Lowest minus highest diversity": positive = less diverse pools go with
                        more repetition.
    contrast_strata     the same with the fifths formed inside bifolium x stratum (exact word length, pool-size tertile,
                        or their product), cells under `min_cell` tokens dropped: the joint control of 28 October 2026.
    lobo_linear         leave-one-bifolium-out percent reduction of squared error of a straight line in the measure.
    joint_within        within-bifolium standardized regression of the outcome on two measures at once.
    shuffle_rank        how many shuffle realizations an observed value exceeds.
All take numpy arrays over tokens plus a `mask` of the cohort (typically outcomes['full'] & finite measure).
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def pooled(v: np.ndarray) -> float:
    t = v.sum(0)
    return float(t[0] / t[1] - t[2] / t[3])


def _bootstrap(v, reps, rng):
    draw = rng.integers(0, len(v), (reps, len(v)))
    s = v[draw].sum(1)
    ok = (s[:, 1] > 0) & (s[:, 3] > 0)
    bs = s[ok, 0] / s[ok, 1] - s[ok, 2] / s[ok, 3]
    return [float(q) for q in np.quantile(bs, [.025, .975])]


def quintile_contrast(metric, outcome, bif, mask, reps=2000, rng=None, min_bif=25, low=.2, high=.8) -> dict:
    """{diff, ci, bifolia, low, high}: low/high are the pooled outcome means of the two fifths."""
    rng = rng or np.random.default_rng(27102026)
    rows = []
    for b in np.unique(bif[mask]):
        m = mask & (bif == b) & np.isfinite(metric) & np.isfinite(outcome)
        if m.sum() < min_bif:
            continue
        x, y = metric[m], outcome[m]
        lo, hi = np.quantile(x, [low, high])
        L, H = y[x <= lo], y[x >= hi]
        rows.append([L.sum(), len(L), H.sum(), len(H)])
    if not rows:
        return dict(diff=float('nan'), ci=[float('nan')] * 2, bifolia=0)
    v = np.array(rows, dtype=float)
    t = v.sum(0)
    out = dict(diff=pooled(v), ci=[float('nan')] * 2, bifolia=len(v), low=float(t[0] / t[1]), high=float(t[2] / t[3]))
    if reps and len(v) >= 3:
        out['ci'] = _bootstrap(v, reps, rng)
    return out


def contrast_strata(metric, outcome, bif, strata, mask, reps=0, rng=None, min_cell=20) -> dict:
    """Fifths formed inside bifolium x stratum; cells under min_cell tokens dropped; pooled contrast with a
    bifolium-resampled interval. `covered` counts the tokens that entered a cell."""
    rng = rng or np.random.default_rng(28102026)
    rows = {}
    covered = 0
    for b in np.unique(bif[mask]):
        acc = np.zeros(4)
        mb = mask & (bif == b) & np.isfinite(metric) & np.isfinite(outcome)
        for s in np.unique(strata[mb]):
            m = mb & (strata == s)
            if m.sum() < min_cell:
                continue
            x, y = metric[m], outcome[m]
            lo, hi = np.quantile(x, [.2, .8])
            L, H = y[x <= lo], y[x >= hi]
            acc += [L.sum(), len(L), H.sum(), len(H)]
            covered += int(m.sum())
        if acc[1] > 0 and acc[3] > 0:
            rows[b] = acc
    if len(rows) < 3:
        return dict(diff=float('nan'), ci=[float('nan')] * 2, covered=covered, bifolia=len(rows))
    v = np.array(list(rows.values()), float)
    r = dict(diff=pooled(v), ci=[float('nan')] * 2, covered=covered, bifolia=len(v))
    if reps:
        r['ci'] = _bootstrap(v, reps, rng)
    return r


def length_strata(words, lo=2, hi=9) -> np.ndarray:
    """Exact word length, clipped to [lo, hi]."""
    return np.clip(np.array([len(w) for w in words]), lo, hi)


def pool_size_tertiles(n, mask) -> np.ndarray:
    """0/1/2 by tertile of pool size among the cohort."""
    q = np.nanpercentile(np.asarray(n, float)[mask], [33, 67])
    return np.digitize(np.asarray(n, float), q)


def joint_strata(words, n, mask) -> np.ndarray:
    """Exact length x pool-size tertile (the joint control)."""
    return length_strata(words) * 10 + pool_size_tertiles(n, mask)


def three_contrasts(metric, outcome, bif, words, n, mask, reps=0, rng=None, min_cell=20) -> dict:
    """raw / inside exact length / inside exact length x pool-size tertile (residual_check.py)."""
    return dict(raw=contrast_strata(metric, outcome, bif, np.zeros(len(outcome), int), mask, reps, rng, min_cell=max(min_cell, 25)),
                length=contrast_strata(metric, outcome, bif, length_strata(words), mask, reps, rng, min_cell),
                length_pool=contrast_strata(metric, outcome, bif, joint_strata(words, n, mask), mask, reps, rng, min_cell))


def lobo_linear(metric, outcome, bif, mask) -> float:
    m = mask & np.isfinite(metric) & np.isfinite(outcome)
    x, y, g = metric[m], outcome[m], bif[m]
    base = err = 0.0
    for b in np.unique(g):
        tr = g != b
        te = ~tr
        if tr.sum() < 50 or te.sum() == 0:
            continue
        X = np.column_stack([np.ones(tr.sum()), x[tr]])
        beta = np.linalg.lstsq(X, y[tr], rcond=None)[0]
        base += ((y[te] - y[tr].mean()) ** 2).sum()
        err += ((y[te] - (beta[0] + beta[1] * x[te])) ** 2).sum()
    return float(100 * (base - err) / base) if base else float('nan')


def joint_within(x1, x2, y, bif, mask) -> dict:
    """Within-bifolium standardized coefficients of y on x1 and x2 (log2 of two diversity measures, typically)."""
    m = mask & np.isfinite(x1) & np.isfinite(x2) & np.isfinite(y)
    cols = []
    for v in (x1, x2, y):
        z = v[m].astype(float).copy()
        for b in np.unique(bif[m]):
            mm = bif[m] == b
            z[mm] -= z[mm].mean()
        cols.append(z / (z.std() or 1))
    X = np.column_stack([cols[0], cols[1]])
    beta = np.linalg.lstsq(X, cols[2], rcond=None)[0]
    return dict(first=float(beta[0]), second=float(beta[1]), r_first=float(np.corrcoef(cols[0], cols[2])[0, 1]),
                r_second=float(np.corrcoef(cols[1], cols[2])[0, 1]), r_between=float(np.corrcoef(cols[0], cols[1])[0, 1]), n=int(m.sum()))


def paired_contrast(metric_a, metric_b, outcome, bif, mask, reps=2000, rng=None, min_bif=25) -> dict:
    """Two contrasts on the same tokens and bifolia (e.g. the cone above against the cone below) and their difference,
    with one bifolium resampling for all three (direction_check.py)."""
    rng = rng or np.random.default_rng(28102026)
    rows = []
    for b in np.unique(bif[mask]):
        m = mask & (bif == b) & np.isfinite(metric_a) & np.isfinite(metric_b) & np.isfinite(outcome)
        if m.sum() < min_bif:
            continue
        y = outcome[m]
        cells = []
        for x in (metric_a[m], metric_b[m]):
            lo, hi = np.quantile(x, [.2, .8])
            L, H = y[x <= lo], y[x >= hi]
            cells += [L.sum(), len(L), H.sum(), len(H)]
        rows.append(cells)
    if len(rows) < 3:
        return dict(a=float('nan'), b=float('nan'), diff=float('nan'), ci=[float('nan')] * 2, bifolia=len(rows))
    v = np.array(rows, float)
    a, b = pooled(v[:, :4]), pooled(v[:, 4:])
    draw = rng.integers(0, len(v), (reps, len(v)))
    s = v[draw].sum(1)
    da = s[:, 0] / s[:, 1] - s[:, 2] / s[:, 3]
    db = s[:, 4] / s[:, 5] - s[:, 6] / s[:, 7]
    d = da - db
    return dict(a=a, b=b, diff=a - b, ci=[float(q) for q in np.quantile(d, [.025, .975])],
                ci_a=[float(q) for q in np.quantile(da, [.025, .975])], ci_b=[float(q) for q in np.quantile(db, [.025, .975])], bifolia=len(v))


def shuffle_rank(values, observed) -> dict:
    """The observed value against K shuffle values: mean, range, rank (shuffles the observation exceeds), the one-sided
    permutation probability (K - rank + 1) / (K + 1), and the EXCESS over the shuffle mean, which is the quantity to
    compare between texts (each text against its own baseline in its own geometry). Nineteen shuffles resolve nothing
    below p = 0.05, thirty nothing below 0.032; choose the comparisons before looking at the values."""
    values = np.asarray(values, float)
    k = int(len(values))
    rank = int((values < observed).sum())
    return dict(observed=float(observed), mean=float(values.mean()), min=float(values.min()), max=float(values.max()), rank=rank, of=k,
                p_one_sided=float((k - rank + 1) / (k + 1)), excess=float(observed - values.mean()))


def interior_mask(line_words, pool_n, min_pool=15, skip_top_lines=0, ms=None) -> np.ndarray:
    """Interior targets: not the first or last word of their line and a pool of at least `min_pool` words; with
    skip_top_lines > 0 also not in the first lines of the page (needs `ms`)."""
    pos = np.concatenate([np.arange(len(ws)) for ws in line_words])
    ln = np.concatenate([np.full(len(ws), len(ws)) for ws in line_words])
    m = (pos > 0) & (pos < ln - 1) & (np.asarray(pool_n) >= min_pool)
    if skip_top_lines and ms is not None:
        lip = np.concatenate([np.full(len(ws), l - ms.pages[ms.lines[l]['page']]['start_line']) for l, ws in enumerate(line_words)])
        m &= lip >= skip_top_lines
    return m


# ---- the standard report: every measure x every control x every cohort, in one call
MEASURES = ('components', 'h2', 'worddiv')
CONTROLS = ('raw', 'length', 'length_pool')


def cohort_masks(line_words, base, pool_n, above_pool_n=None, min_pool=15) -> Dict[str, np.ndarray]:
    """The cohorts of the interior checks: 'all' (complete windows inside the bifolium, valid scores); 'interior-A'
    (also not the first or last word of its line, and the study pool holds at least min_pool words); 'interior-B' (the
    same with the lines-above pool, when given). Edge words have truncated windows and low measured diversity whatever
    the text, which masked the vertical association in every earlier cut (RESULTS section 7 item 9)."""
    pos = np.concatenate([np.arange(len(ws)) for ws in line_words])
    ln = np.concatenate([np.full(len(ws), len(ws)) for ws in line_words])
    inner = base & (pos > 0) & (pos < ln - 1)
    out = {'all': base, 'interior-A': inner & (np.asarray(pool_n) >= min_pool)}
    if above_pool_n is not None:
        out['interior-B'] = inner & (np.asarray(above_pool_n) >= min_pool)
    return out


def standard_contrasts(table, out, bif, words, mask, measures=MEASURES, outcome='app_impact', cohorts=None, line_words=None,
                       above_table=None, reps=0, rng=None, min_cell=20) -> dict:
    """All of it at once, so that no control is dropped when another is added (the fault the 28 October 2026 audit
    found): for each measure (components, H2, word diversity), the within-bifolium contrast of `outcome` raw, inside
    exact word length, and inside exact length x pool-size tertile; on each cohort ('all', and the interior cohorts when
    `line_words` is given). `table` is a score() result (needs 'n'); `out` an outcomes() result.
    Returns {cohort: {'n', 'mean_pool', measure: {control: {diff, ci, covered, bifolia}}}}."""
    y = out[outcome]
    valid = mask & np.all([np.isfinite(table[m]) for m in measures], axis=0)
    if cohorts is None:
        cohorts = cohort_masks(line_words, valid, table['n'], above_table['n'] if above_table else None) if line_words is not None else {'all': valid}
    result = {}
    for cname, cm in cohorts.items():
        cm = cm & valid
        r = dict(n=int(cm.sum()), mean_pool=float(np.nanmean(np.asarray(table['n'], float)[cm])) if cm.any() else float('nan'))
        for m in measures:
            r[m] = three_contrasts(table[m], y, bif, words, table['n'], cm, reps=reps, rng=rng, min_cell=min_cell)
        result[cname] = r
    return result


def format_contrasts(result: dict, title: str = '') -> str:
    """A text table of standard_contrasts()."""
    lines = [title] if title else []
    for cname, r in result.items():
        lines.append('  cohort %-11s n %6d  mean pool %.1f' % (cname, r['n'], r['mean_pool']))
        for m in MEASURES:
            if m not in r:
                continue
            cells = []
            for c in CONTROLS:
                v = r[m][c]
                cells.append(('%+.3f [%+.3f,%+.3f]' % (v['diff'], v['ci'][0], v['ci'][1])) if np.isfinite(v['ci'][0]) else '%+.3f' % v['diff'])
            lines.append('    %-11s raw %22s   inside length %22s   inside length x pool %22s' % (m, *cells))
    return '\n'.join(lines)


def baseline_summary(observed: dict, shuffles) -> dict:
    """observed and each shuffle: standard_contrasts() results of the SAME cohorts and geometry. Returns, per cohort,
    measure and control, shuffle_rank() of the observed value: the excess over the baseline and its rank."""
    out = {}
    for cname in observed:
        out[cname] = {}
        for m in MEASURES:
            if m not in observed[cname]:
                continue
            out[cname][m] = {}
            for c in CONTROLS:
                vals = [s[cname][m][c]['diff'] for s in shuffles if cname in s]
                out[cname][m][c] = shuffle_rank(vals, observed[cname][m][c]['diff'])
    return out


def format_baseline(summary: dict, title: str = '') -> str:
    lines = [title] if title else []
    for cname, r in summary.items():
        lines.append('  cohort %s' % cname)
        for m, cc in r.items():
            cells = ['%s %+.3f vs %+.3f (%+.3f..%+.3f) excess %+.3f rank %d/%d p %.3f' % (c, v['observed'], v['mean'], v['min'], v['max'], v['excess'], v['rank'], v['of'], v['p_one_sided']) for c, v in cc.items()]
            lines.append('    %-11s ' % m + ' | '.join(cells))
    return '\n'.join(lines)
