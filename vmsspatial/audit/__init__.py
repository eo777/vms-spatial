"""The alignment review: how every ZL token is associated with the Voynichese Project's word rectangles, what was
flagged, and which tokens are allowed into spatial calculations.

    flags       the flag taxonomy and the strict / sensitivity policies
    review      read the review (data/manuscript/spatial_review.json.gz): geometry per policy, per-token records, per-page
                summaries, the packaging into a word bundle
    checks      invariants of the review file and of a bundle built from it
"""
from .flags import FLAGS, HARD, STRICT, POLICIES, QUARANTINE  # noqa: F401
from .review import load_review, geometry, package, token_table, flagged_tokens, page_summary, describe_token  # noqa: F401
