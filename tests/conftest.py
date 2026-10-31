import sys
from pathlib import Path

import pytest

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT))

from vmsspatial import paths  # noqa: E402


def _have(key):
    return paths.resolve(key, required=False) is not None


needs_data = pytest.mark.skipif(not _have('manuscript/words.json.gz') or not _have('manuscript/tokens.json'), reason='data folder not populated (vmsspatial fetch-data)')
needs_raw = pytest.mark.skipif(not _have('raw/ZL_ivtff_raw.txt'), reason='the ZL transliteration is not present')
needs_controls = pytest.mark.skipif(not _have('controls/streams/m_timm/generated_text.txt') or not _have('controls/texts/de_gart_augsburg1487.txt'), reason='control texts not present')


# The public defaults: every page and locus of the recorded manuscript, folio order, the flat warp state.
@pytest.fixture(scope='session')
def ms():
    from vmsspatial import Manuscript
    return Manuscript.load()


@pytest.fixture(scope='session')
def strict():
    from vmsspatial import load_bundle
    return load_bundle('strict')


@pytest.fixture(scope='session')
def sensitivity():
    from vmsspatial import load_bundle
    return load_bundle('sensitivity')


@pytest.fixture(scope='session')
def sensitivity_recorded():
    """The default shape in the recorded warp state (what the warp and the frames are fitted on)."""
    from vmsspatial import load_bundle
    return load_bundle('sensitivity', warp='recorded')


# The shape of the October 2026 studies: the paragraph text of 207 pages, Path 1 order, recorded rectangles.
@pytest.fixture(scope='session')
def ms_study():
    from vmsspatial import Manuscript
    from vmsspatial.manuscript import STUDY
    return Manuscript.load(**STUDY)


@pytest.fixture(scope='session')
def strict_study():
    from vmsspatial import load_bundle
    from vmsspatial.manuscript import STUDY
    return load_bundle('strict', warp='recorded', **STUDY)


@pytest.fixture(scope='session')
def sensitivity_study():
    from vmsspatial import load_bundle
    from vmsspatial.manuscript import STUDY
    return load_bundle('sensitivity', warp='recorded', **STUDY)


@pytest.fixture(scope='session')
def review():
    from vmsspatial.audit import load_review
    return load_review()


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: takes more than about ten seconds')
