"""vmsspatial: 2-D spatial analysis of the Voynich manuscript text on its recorded word rectangles.

Analysis toolset of the vms-spatial project. The main entry points:

    from vmsspatial import Manuscript, load_bundle, SpatialContext, PoolSpec
    ms = Manuscript.load()                          # 227 pages, 5,365 lines, 38,876 tokens: every recorded locus, by bifolium
    bundle = load_bundle('strict')                  # words, lines, reviewed word rectangles (flat warp state), components
    # the 2026 studies' shape: Manuscript.load(pages='paragraph', order='path1'), load_bundle(..., warp='recorded')
    ctx = SpatialContext(bundle)                    # per-page geometry: centres, word width, line pitch
    table = ctx.score(PoolSpec())                   # per-token pool measures (components, H2, word diversity, pool size)

See README.md for the layout of the package.
"""
from .manuscript import Manuscript, tokenize, GROUP_SECTION, group_label, group_labels  # noqa: F401
from .bundle import load_bundle, make_bundle, save_bundle, validate_bundle, POLICIES  # noqa: F401
from .selector import PoolSpec, Pool, SpatialContext, STUDY_SELECTOR  # noqa: F401
from .measures import Features, measure, mattr, bag_mattr, iid_mattr, trailing_distinct, fresh_indicator, rolling_series, mean_within  # noqa: F401
from .outcomes import outcomes, word_impact, token_meta  # noqa: F401
from .geometry import line_frames, oversized_flags, vertical_gaps, place_in_slot, fill_slots, synthetic_geometry, PageGeometry, Layout  # noqa: F401
from .baselines import glyph_effects, word_baselines, baseline_rms, line_xheights  # noqa: F401
from .flatten import flatten  # noqa: F401
from .ink import load_ink, intrusions  # noqa: F401
from .units import zattera, letters  # noqa: F401
from . import compare, wheels  # noqa: F401                  # the comparison model and the wheels; `from vmsspatial import plot` needs matplotlib

__version__ = '0.1.0'
