"""Coverage of the recorded rectangles: per page and locus type, how many ZL tokens have a usable box.

    rows = coverage(review, bundle)          # one row per (page, locus type) and a total row per page
    write_coverage(rows, 'coverage_by_page.csv')

Columns: page, locus_type, zl_tokens (every canonical ZL token of that page and type, uncertain readings included),
xml_words (the Voynichese Project's rectangles assigned to tokens of that type; the page's total row adds the
rectangles assigned to no token), bundle_tokens (tokens in the extra bundle: uncertain readings omitted), located_strict,
located_sensitivity, share_strict, share_sensitivity (of bundle_tokens), kind (the orientation kinds of the type's lines
in the bundle, counted), detected (fRos: boxes found on the image at or above the confidence floor), and why a ZL token
of a coordinate page has no usable box: no_xml_word (the XML has no word there, the rare glyphs among them),
transcriptions_differ (a free rectangle stands there but the spellings and word counts disagree), position_failed (a free
rectangle has the spelling but fails the line or the reading order), invalid_box (the recorded rectangle has no width)
and disconnected_parts (the word's pieces lie apart along its line). The page total row has locus_type 'all'.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from typing import List, Optional

from .flags import UNLOCATED_REASONS
from .review import load_review

REASONS = UNLOCATED_REASONS + ('invalid_box', 'disconnected_parts')


def coverage(review: Optional[dict] = None, bundle: Optional[dict] = None) -> List[dict]:
    """Per page and locus type (``module docstring``). `bundle` defaults to ``load_bundle('sensitivity',
    warp='recorded')`` (every page and locus); the strict count comes from the review's per-token eligibility, the
    sensitivity count from the bundle's geometry."""
    review = review or load_review()
    if bundle is None:
        from ..bundle import load_bundle
        bundle = load_bundle('sensitivity', warp='recorded')
    from ..orientation import attach
    attach(bundle)
    zl = Counter()
    reasons = defaultdict(Counter)
    xml_assigned = defaultdict(set)
    xml_only = defaultdict(set)
    for t in review['tokens']:
        zl[(t['page'], t['locus_type'])] += 1
        for f in REASONS:
            if f in t['flags']:
                reasons[(t['page'], t['locus_type'])][f] += 1
        if t['group']:
            g = review['groups'][t['group']]
            for i in g.get('xml_indices', []):
                xml_assigned[(t['page'], t['locus_type'])].add(i)
    for g in review['groups'].values():
        if not g['tokens']:
            for i in g.get('xml_indices', []):
                xml_only[g['page']].add(i)
    by_id = {t['id']: t for t in review['tokens']}
    bt = Counter()
    loc_s = Counter()
    loc_sens = Counter()
    kinds = defaultdict(Counter)
    detected = Counter()
    conf = bundle.get('detected_confidence') or {}
    sr = bundle.get('spatialReview')
    for L in bundle['lines']:
        key = (L['page'], L.get('locus_type'))
        kinds[key][L['orientation']['kind']] += 1
        for i in range(L['start'], L['end']):
            bt[key] += 1
            if bundle['geometry'][i]:
                loc_sens[key] += 1
            if sr:
                t = by_id.get(sr['tokens'][i]['id'])
                if t and t['strict']:
                    loc_s[key] += 1
            if str(i) in conf:
                detected[key] += 1
    rows = []
    pages = sorted({k[0] for k in zl} | {k[0] for k in bt}, key=_folio_key)
    for p in pages:
        types = sorted({k[1] for k in zl if k[0] == p} | {k[1] for k in bt if k[0] == p}, key=lambda t: (t or '?'))
        tot = dict(zl_tokens=0, xml_words=len(xml_only[p]), bundle_tokens=0, located_strict=0, located_sensitivity=0, detected=0, **{f: 0 for f in REASONS})
        kind_tot = Counter()
        for t in types:
            k = (p, t)
            row = dict(page=p, locus_type=t, zl_tokens=zl[k], xml_words=len(xml_assigned[k]), bundle_tokens=bt[k], located_strict=loc_s[k], located_sensitivity=loc_sens[k],
                       detected=detected[k], kind=' '.join('%s:%d' % kv for kv in sorted(kinds[k].items())), **{f: reasons[k][f] for f in REASONS})
            row['share_strict'] = round(row['located_strict'] / row['bundle_tokens'], 3) if row['bundle_tokens'] else None
            row['share_sensitivity'] = round(row['located_sensitivity'] / row['bundle_tokens'], 3) if row['bundle_tokens'] else None
            rows.append(row)
            for f in ('zl_tokens', 'bundle_tokens', 'located_strict', 'located_sensitivity', 'detected') + REASONS:
                tot[f] += row[f]
            tot['xml_words'] += row['xml_words']
            kind_tot.update(kinds[k])
        total = dict(page=p, locus_type='all', **tot, kind=' '.join('%s:%d' % kv for kv in sorted(kind_tot.items())))
        total['share_strict'] = round(tot['located_strict'] / tot['bundle_tokens'], 3) if tot['bundle_tokens'] else None
        total['share_sensitivity'] = round(tot['located_sensitivity'] / tot['bundle_tokens'], 3) if tot['bundle_tokens'] else None
        rows.append(total)
    return rows


def totals(rows: List[dict]) -> dict:
    """Sums over the page total rows, and per locus type."""
    out = dict(pages=0, zl_tokens=0, xml_words=0, bundle_tokens=0, located_strict=0, located_sensitivity=0, detected=0, by_type={}, **{f: 0 for f in REASONS})
    by = defaultdict(Counter)
    for r in rows:
        if r['locus_type'] == 'all':
            out['pages'] += 1
            for f in ('zl_tokens', 'xml_words', 'bundle_tokens', 'located_strict', 'located_sensitivity', 'detected') + REASONS:
                out[f] += r[f]
        else:
            for f in ('zl_tokens', 'bundle_tokens', 'located_strict', 'located_sensitivity', 'detected') + REASONS:
                by[r['locus_type']][f] += r[f]
    out['by_type'] = {t: dict(c) for t, c in sorted(by.items(), key=lambda kv: str(kv[0]))}
    return out


FIELDS = ('page', 'locus_type', 'zl_tokens', 'xml_words', 'bundle_tokens', 'located_strict', 'located_sensitivity', 'share_strict', 'share_sensitivity', 'detected', 'kind') + REASONS


def write_coverage(rows: List[dict], path):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS), extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _folio_key(f: str):
    import re
    m = re.match(r'^f(\d+)([rv])(\d*)$', f or '')
    return (int(m.group(1)), m.group(2), int(m.group(3) or 0)) if m else (10 ** 6, f, 0)
