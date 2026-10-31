"""matplotlib renders: every plot function draws into a buffer and the axes hold the expected artists; no PNG is kept."""
import io

import pytest

from conftest import needs_data

matplotlib = pytest.importorskip('matplotlib')
matplotlib.use('Agg')

from vmsspatial import plot as P  # noqa: E402


def _png(ax):
    buf = io.BytesIO()
    ax.figure.savefig(buf, format='png', dpi=40)
    matplotlib.pyplot.close(ax.figure)
    return len(buf.getvalue())


@needs_data
@pytest.mark.slow
def test_page_renders(ms, sensitivity):
    ax = P.plot_page('f75r', bundle=sensitivity)
    title = ax.get_title(loc='left')
    assert 'f75r' in title and 'flat warp' in title and 'recorded frame' in title and 'data' in title
    assert len(ax.patches) == 418 and len(ax.lines) == 53                             # one polygon per unit, one baseline polyline per line
    assert ax.yaxis_inverted()
    assert _png(ax) > 1000
    ax = P.plot_page('f68r2', bundle=sensitivity, show=('boxes', 'orientation'), color_by='kind', labels=True)
    assert len(ax.texts) > 10 and ax.figure.legends and ax.get_legend() is None                 # the legend sits under the axes, never over the boxes
    assert any(l.get_linestyle() == ':' for l in ax.lines)                            # the fitted circles of the circular lines
    _png(ax)
    ax = P.plot_page('f116v', bundle=sensitivity)                                      # a page without rectangles says so
    assert 'no geometry' in ax.get_title(loc='left')
    _png(ax)


@needs_data
@pytest.mark.slow
def test_comparison_wheels_and_bifolium(ms, sensitivity_recorded):
    from vmsspatial import compare as C
    data = C.prepare(sensitivity_recorded, ms, baseline='glyph')
    ax = P.plot_comparison('f20v', 'f21r', cutoff=3, data=data, baseline='glyph')
    t = ax.get_title(loc='left')
    assert 'Dice' in t and 'direct-overlap EVA' in t and 'nearby EVA' in t and 'flat warp' in t and ax.figure.legends and ax.get_legend() is None
    assert len(ax.patches) > 20 and ax.figure.get_size_inches()[1] >= 4.5                        # readable at the default size
    _png(ax)
    axes = P.plot_comparison('f20v', 'f21r', cutoff=3, mode='side', data=data, baseline='glyph', drift=True)
    assert len(axes) == 2 and axes[0].get_title(loc='left').startswith('f20v') and axes[0].figure.legends
    assert len(axes[0].figure.legends[0].get_texts()) == 4                                      # two pages, two drift guides
    _png(axes[0])
    ax = P.plot_wheel('f68r2', bundle=sensitivity_recorded)
    t = ax.get_title(loc='left')
    assert '2 wheel(s)' in t and 'recorded frame' in t and ax.figure.legends
    _png(ax)
    ax = P.plot_centered_wheels('fRos', bundle=sensitivity_recorded)
    assert 'display frame' in ax.get_title(loc='left') and '9 wheels' in ax.get_title(loc='left')
    _png(ax)
    axes = P.plot_bifolium('C:20-21', 'inner', bundle=sensitivity_recorded, warp='recorded')
    assert axes[0].get_title(loc='left').startswith('f20v') and axes[1].get_title(loc='left').startswith('f21r')
    _png(axes[0])
    with pytest.raises(KeyError):
        P.plot_wheel('f75r', wheel=1, bundle=sensitivity_recorded)
