import pytest

from conftest import needs_data

from vmsspatial.audit import FLAGS, HARD, STRICT, geometry, package, flagged_tokens, page_summary, describe_token
from vmsspatial.audit.checks import check_review, check_bundle, all_ok


def test_flag_taxonomy_covers_the_policies():
    assert HARD <= STRICT
    assert all(f in FLAGS for f in STRICT)
    assert 'uncertain_boundary' in FLAGS and 'exact_compound_union' in FLAGS


@needs_data
def test_review_counts_and_policies(review):
    assert len(review['tokens']) == 39026 and review['version'] == '2026-10-31'
    g = geometry(review)
    assert sum(1 for b in g.values() if b) == 35286
    assert sum(1 for b in geometry(review, 'sensitivity').values() if b) == 38325
    with pytest.raises(ValueError):
        geometry(review, 'legacy')
    assert set(review['policies']['strict_exclusions']) == STRICT
    for k in ('provenance', 'repairs', 'original_groups'):
        assert k not in review                                   # the review is the data product, not a log of its making
    assert not any('repair' in g or 'cost' in g for g in review['groups'].values())
    t = describe_token(review, 'f75r.42@32:39')
    assert t['token']['text'] == 'qokeedy' and t['group']['xml_indices'] == [371] and 'alignment_reviewed' in t['flags']
    assert page_summary(review)['f75r']['strict'] == 418
    rows = flagged_tokens(review, ['image_reviewed_boundary'])
    assert len(rows) == 18 and all(r['page'] == 'f75r' for r in rows)


@needs_data
def test_review_invariants(review, strict, strict_study):
    rep = check_review(review)
    assert all_ok(rep), {k: v for k, v in rep.items() if not v.get('ok')}
    for bundle in (strict, strict_study):                        # the default bundle (every locus, flat) and the study shape
        rep = check_bundle(bundle, review)
        assert all_ok(rep), {k: v for k, v in rep.items() if not v.get('ok')}


@needs_data
def test_package_reproduces_the_bundle_block(review, strict_study, strict):
    sr = package(review, strict_study['words'], strict_study['lines'])
    assert sr['geometry'] == strict_study['spatialReview']['geometry']
    assert sr['sensitivityGeometry'] == strict_study['spatialReview']['sensitivityGeometry']
    assert [t['id'] for t in sr['tokens']] == [t['id'] for t in strict_study['spatialReview']['tokens']]
    assert set(sr['groups']) == set(strict_study['spatialReview']['groups'])
    full = package(review, strict['words'], strict['lines'])     # the default bundle: the same records by bifolium, fRos's detected groups added by the bundle
    assert [t['id'] for t in full['tokens']] == [t['id'] for t in strict['spatialReview']['tokens']]
    assert set(full['groups']) <= set(strict['spatialReview']['groups'])
