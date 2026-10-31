"""Invariants of a review file, and of a word bundle built from it.

    check_review(review)          every token assigned once or unassigned; strict geometry only from single-word
                                  assignments or provenanced resolutions; groups stay on their page; the metrics agree
                                  with the records
    check_bundle(bundle, review)  the bundle's words and review records agree; the strict mask matches the geometry;
                                  strict pools cannot reach an excluded location
Each returns a report dict: {name: {ok: bool, detail}}.
"""
from __future__ import annotations

from typing import Optional


def check_review(review: dict) -> dict:
    tokens = {t['id']: t for t in review['tokens']}
    groups = review['groups']
    report = {}
    ids = [i for g in groups.values() for i in g['tokens']]
    unassigned = sum(t['group'] is None for t in tokens.values())
    report['no_token_lost_or_duplicated'] = dict(ok=len(ids) == len(set(ids)) and len(ids) + unassigned == len(tokens),
                                                 assigned=len(ids), unassigned=unassigned, tokens=len(tokens))
    bad = []
    for t in tokens.values():
        if not t['strict']:
            continue
        g = groups[t['group']]
        if 'resolved_box' in t:
            r = next((r for r in g.get('resolved', []) if r['token'] == t['id']), None)
            if r is None or t['resolved_box'] != r['box'] or r['method'] not in ('exact_compound_union', 'image_reviewed_boundary'):
                bad.append(t['id'])
            elif r['method'] == 'exact_compound_union' and (t['text'] != ''.join(g['xml_words']) or len(g['tokens']) != 1):
                bad.append(t['id'])
        elif not (len(g['tokens']) == 1 and len(g['parts']) == 1 and g['box'] == g['parts'][0]):
            bad.append(t['id'])
    report['strict_geometry_is_single_word_or_resolved'] = dict(ok=not bad, offenders=bad[:20], count=len(bad))
    report['groups_stay_on_their_page'] = dict(ok=all(tokens[i]['page'] == g['page'] for g in groups.values() for i in g['tokens'] if i in tokens))
    m = review['metrics']
    report['metrics_consistent'] = dict(ok=m['canonical_tokens'] == len(tokens) and m['strict_eligible'] == sum(t['strict'] for t in tokens.values())
                                        and m['sensitivity_eligible'] == sum(t['sensitivity'] for t in tokens.values()))
    return report


def check_bundle(bundle: dict, review: Optional[dict] = None) -> dict:
    from ..selector import SpatialContext
    report = {}
    sr = bundle.get('spatialReview')
    report['reviewed_bundle'] = dict(ok=bool(sr) and bundle.get('schema') == 3, schema=bundle.get('schema'), version=sr['version'] if sr else None)
    if not sr:
        return report
    report['review_tokens_match_words'] = dict(ok=[t['text'] for t in sr['tokens']] == bundle['words'] and len(sr['tokens']) == len(bundle['geometry']))
    report['strict_geometry_matches_mask'] = dict(ok=all((b is not None) == t['strict'] for b, t in zip(bundle['geometry'], sr['tokens'])))
    ctx = SpatialContext(bundle)
    leaks = 0
    for i in range(0, ctx.n, 19):
        p = ctx.pool(i)
        leaks += sum(1 for j in p.indices if not sr['tokens'][j]['strict'])
    report['strict_pools_hold_strict_tokens_only'] = dict(ok=leaks == 0, leaks=leaks)
    if review is not None:
        by_id = {t['id']: t for t in review['tokens']}
        # a detected group (fRos) is the bundle's own addition: its tokens are located by the toolkit, not by the review
        report['bundle_records_are_review_records'] = dict(ok=all(by_id[t['id']]['text'] == t['text'] and (by_id[t['id']]['strict'] == t['strict'] or 'detected' in (t.get('flags') or [])) for t in sr['tokens']))
    return report


def all_ok(report: dict) -> bool:
    return all(v.get('ok') for v in report.values())
