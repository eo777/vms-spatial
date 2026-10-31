"""Printing pages with matplotlib: a page's rectangles and baselines, a comparison overlay, a wheel, the centred
wheels of a page, a bifolium face. For when the web atlas is not at hand.

    from vmsspatial import plot
    plot.plot_page('f75r').figure.savefig('f75r.png')                 # the flat state, boxes and baselines
    plot.plot_page('f75r', image='display')                          # on the Voynichese display image, recorded coordinates
    plot.plot_comparison('f20v', 'f21r', cutoff=3)                   # two openings overlaid, the scores in the title
    plot.plot_wheel('f68r2'); plot.plot_centered_wheels('fRos')
    plot.plot_bifolium('C:20-21', 'inner')

Every figure names the frame and the warp state of what it draws and the data version. Nothing drawn on a page image
is in the flat state: with `image`, the geometry is converted to recorded coordinates first and mapped through the
stored registration (``vmsspatial.images``). The Agg backend is used so that rendering needs no display; the
functions return the Axes and leave saving to the caller (``vmsspatial plot f75r --out f75r.png`` does both).
matplotlib is an optional dependency (``pip install vms-spatial[plot]``).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import paths

KIND_COLOURS = {'horizontal': '#2875a8', 'rotated': '#c56939', 'circular': '#438e79', 'radial': '#9751aa', 'label': '#b79826', 'unknown': '#8a8f93'}
PAIR_COLOURS = ['#2875a8', '#c56939', '#438e79', '#9751aa', '#b79826', '#4e62bc', '#ad5b7f', '#5d8f9d']
COLOR_MODES = ('kind', 'line', 'paragraph')
WORD_DIRECTIONS = ('ring', 'level')
_LOADED: Dict[str, object] = {}


def _plt():
    import matplotlib
    if matplotlib.get_backend().lower() not in ('agg', 'module://matplotlib_inline.backend_inline'):
        try:
            matplotlib.use('Agg')
        except Exception:
            pass
    import matplotlib.pyplot as plt
    return plt


def data_version() -> str:
    """The data manifest's version (named in every title)."""
    try:
        return str(paths.manifest().get('version'))
    except Exception:
        return '?'


def _ms():
    if 'ms' not in _LOADED:
        from .manuscript import Manuscript
        _LOADED['ms'] = Manuscript.load()
    return _LOADED['ms']


def _bundle(bundle, warp: str, policy: str = 'sensitivity'):
    """The bundle to draw: the one given, else the manuscript bundle under `policy` in the asked warp state."""
    if bundle is not None:
        return bundle
    key = ('bundle', policy, warp)
    if key not in _LOADED:
        from .bundle import load_bundle
        _LOADED[key] = load_bundle(policy, warp=warp)
    return _LOADED[key]


def _page_lines(app, ms, folio: str):
    p = ms.page(folio)
    return p, [(l, app['lines'][l]) for l in range(p['start_line'], p['end_line'])]


def _axes(ax, width: float, height: float, size: float = 7.0, min_height: float = 2.0):
    plt = _plt()
    if ax is None:
        ratio = (height / width) if width else 1.3
        fig, ax = plt.subplots(figsize=(size, min(12.0, max(min_height, size * ratio))))   # the page's aspect, within a printable height
    return ax


def _legend_below(ax, handles=None, ncol: int = 1, fontsize: int = 7):
    """The legend under the axes, never over the boxes: a figure legend along the bottom edge; ``_finish`` reserves
    the room for it (the axes keep an equal aspect, so an axes-anchored legend would land on the x label)."""
    fig = ax.figure
    if handles is None:
        handles, labels = ax.get_legend_handles_labels()
        if not handles:
            return None
    old = getattr(fig, '_vms_bottom_legend', None)
    if old is not None:
        try:
            old.remove()
        except Exception:
            pass
        handles = list(getattr(fig, '_vms_legend_handles', [])) + list(handles)
    seen, unique = set(), []
    for h in handles:                                              # one entry per label (two panels share 'baselines')
        label = h.get_label() if hasattr(h, 'get_label') else str(h)
        if label not in seen:
            seen.add(label)
            unique.append(h)
    handles = unique
    fig._vms_legend_handles = list(handles)
    rows = max(1, -(-len(handles) // max(1, ncol)))
    fig._vms_bottom_legend = fig.legend(handles=handles, loc='lower center', ncol=ncol, fontsize=fontsize, frameon=False, borderaxespad=0.4)
    fig._vms_legend_rows = rows
    return fig._vms_bottom_legend


def _finish(ax, title: str, xlim, ylim, invert: bool = True):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    if invert and ax.get_ylim()[0] < ax.get_ylim()[1]:
        ax.invert_yaxis()
    ax.set_aspect('equal')
    ax.set_title(title, fontsize=9, loc='left')
    ax.set_xlabel('x (px)')
    ax.set_ylabel('y (px)')
    _margins(ax.figure, title)
    return ax


def _margins(fig, title: str = ''):
    """Explicit figure margins (equal-aspect axes defeat tight_layout): room for a one- or two-line title above and
    the bottom legend's rows below, so neither ever overlaps the axes or its labels."""
    rows = getattr(fig, '_vms_legend_rows', 0)
    bottom = min(0.45, 0.11 + 0.038 * rows) if rows else 0.1
    top = 0.88 if '\n' in title else 0.92
    try:
        fig.subplots_adjust(left=0.1, right=0.97, top=top, bottom=bottom, wspace=0.18)
    except Exception:
        pass


def _baseline_points(app, ms, method: str):
    """Baseline points for the bundle in its own warp state: the shipped table moved with the page warp when the
    bundle is flat and the table was built on its recorded parent, else derived (the ink product's warp warning is
    silenced here: the points are read through the box bottoms, which is coherent, and the title names the state)."""
    import warnings
    from .baselines import word_baselines, load_table, table_points
    from .frames import tags, FrameWarning
    if tags(app)['warp'] == 'flat':
        tbl = load_table()
        if tbl is not None:
            try:
                from .warp import transform
                pts = table_points(app, method, transform(tbl, 'flat'))
                if pts is not None:
                    return pts
            except Exception:
                pass
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', FrameWarning)
        return word_baselines(app, ms, method)


def _atlas_cmap():
    """The atlas's colour scale: warm = low or negative, teal = high or positive."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list('atlas', ['#a83c35', '#d56b43', '#e9aa6c', '#ead6a1', '#a1c5ad', '#4e9c92', '#185965'])


def _to_recorded(app):
    from .frames import tags
    if tags(app)['warp'] == 'flat':
        from .warp import transform
        return transform(app, 'recorded')
    return app


def _word_rotation(line: dict, j: int, word_direction: str) -> float:
    """matplotlib's rotation for token j of a line: minus ``orientation.label_angle``, since matplotlib turns
    anticlockwise on the screen and the page's directions run clockwise; 0 for 'level' or an unknown direction."""
    from .orientation import label_angle
    if word_direction == 'level':
        return 0.0
    angle = label_angle(line.get('orientation'), j)
    return 0.0 if angle is None else -angle


def _check_direction(word_direction: str):
    if word_direction not in WORD_DIRECTIONS:
        raise ValueError('word_direction must be one of %r' % (WORD_DIRECTIONS,))


def plot_page(folio: str, ax=None, bundle=None, warp: str = 'flat', show: Sequence[str] = ('boxes', 'baselines'), color_by: Optional[str] = None, labels: bool = False,
              image: Optional[str] = None, policy: str = 'sensitivity', baseline: str = 'auto', word_direction: str = 'ring'):
    """Draw one page: its recorded word rectangles, its baseline points joined per line, the orientation of rotated
    and circular lines.

    Args:
        folio: the page ('f75r').
        ax: a matplotlib Axes (a new figure sized from the page's aspect when None).
        bundle: the bundle to draw (default the manuscript bundle under `policy`, loaded in the warp state `warp`).
        warp: 'flat' (default: the stored page warp removed) or 'recorded'; ignored with `image` (a page image needs
            recorded coordinates, so the geometry is converted and the title says so).
        show: any of 'boxes', 'baselines', 'orientation' (an arrow along each rotated line, the fitted circle of each
            circular line), 'breaks' (the transcript intrusion breaks).
        color_by: None (one colour), 'kind' (the line's orientation kind), 'line' (alternating), 'paragraph', a key of
            ``line_stats.KEYS`` ('resid_chord', 'chord_flat', 'warp_shift', ...: the atlas's scale, 5-95 percent of the
            whole manuscript, warm = low or negative, teal = high or positive; the title names the measure), or a
            sequence of per-token values (a colour scale).
        labels: write every word in its rectangle.
        image: 'display' or 'beinecke': draw the page image from the cache under the rectangles (downloaded on first
            use), mapping the recorded geometry through the stored registration.
        policy: 'sensitivity' (default: every reviewed rectangle, shared boxes once) or 'strict'.
        baseline: the baseline method ('auto', 'glyph', 'ink', 'centre', 'bottom').
        word_direction: with `labels`, 'ring' (default) writes each word along its line's direction
            (``orientation.label_angle``: a ring word's bottom towards the centre), 'level' writes every word upright.

    Returns:
        the Axes. The title names the frame, the warp state, the policy and the data version.

    Example:
        >>> ax = plot_page('f75r')                      # doctest: +SKIP
        >>> ax.figure.savefig('f75r.png', dpi=150)      # doctest: +SKIP
    """
    from .frames import tags
    from .orientation import attach
    _check_direction(word_direction)
    plt = _plt()
    ms = _ms()
    app = _bundle(bundle, 'recorded' if image else warp, policy)
    attach(app, ms)
    t = tags(app)
    drawn = app
    converted = False
    if image and t['warp'] == 'flat':
        drawn = _to_recorded(app)
        converted = True
    p, lines = _page_lines(drawn, ms, folio)
    geom = drawn['geometry']
    mapping = None
    img = None
    if image:
        from .images import registration, page_image, Mapping
        rec = registration(folio, image)
        if not rec.get('ok'):
            raise ValueError('no registration of %s to the %s image: %s' % (folio, image, rec.get('flags')))
        mapping = Mapping(rec)
        img = page_image(folio, image, rec.get('image_id'))
    boxes = [(l, L, geom[i], i) for l, L in lines for i in range(L['start'], L['end']) if geom[i]]
    if not boxes:
        ax = _axes(ax, 1000, 1400)
        ax.text(0.5, 0.5, '%s: no located rectangles' % folio, ha='center', va='center', transform=ax.transAxes)
        return _finish(ax, '%s (no geometry)' % folio, (0, 1000), (0, 1400))
    xs = [b[2][0] for b in boxes] + [b[2][2] for b in boxes]
    ys = [b[2][1] for b in boxes] + [b[2][3] for b in boxes]
    pad = 40.0

    def to_plot(pts):
        P = np.asarray(pts, float).reshape(-1, 2)
        return mapping.to_image(P) if mapping is not None else P
    if img is not None:
        ax = _axes(ax, img.shape[1], img.shape[0])
        ax.imshow(img, interpolation='bilinear')
    else:
        ax = _axes(ax, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
    # colours
    seen_groups = set()
    review = drawn.get('spatialReview')
    para = np.cumsum([1 if ms.lines[l]['first'] else 0 for l, _ in lines])
    para_of = {l: int(k) for (l, _), k in zip(lines, para)}
    values = None
    measure_name = ''
    if isinstance(color_by, str) and color_by not in COLOR_MODES:
        from .line_stats import KEYS, token_values
        if color_by not in KEYS:
            raise ValueError("color_by must be one of %r, a key of line_stats.KEYS, or per-token values (got %r)" % (COLOR_MODES, color_by))
        spec = KEYS[color_by]
        values = np.asarray([np.nan if v is None else float(v) for v in token_values(color_by, app, ms, baseline)], float)
        cmap = _atlas_cmap()
        lo, hi = spec['domain'] if spec['domain'] else (np.nanpercentile(values, 5), np.nanpercentile(values, 95))
        if spec['kind'] == 'diverging' and not spec['domain']:
            hi = max(abs(lo), abs(hi))
            lo = -hi
        measure_name = spec['label'] + (', ' + spec['unit'] if spec['unit'] else '')
    elif color_by is not None and not isinstance(color_by, str):
        values = np.asarray([np.nan if v is None else float(v) for v in color_by], float)
        cmap = plt.get_cmap('viridis')
        lo, hi = np.nanpercentile(values, 5), np.nanpercentile(values, 95)
    from matplotlib.patches import Polygon, Circle
    legend = {}
    if 'boxes' in show:
        for l, L, b, i in boxes:
            g = review['tokens'][i].get('group') if review else None
            if g and g in seen_groups:
                continue
            if g:
                seen_groups.add(g)
            kind = L['orientation']['kind']
            if values is not None:
                v = values[i]
                col = '#bbbbbb' if not np.isfinite(v) else cmap(0.0 if hi <= lo else float(np.clip((v - lo) / (hi - lo), 0, 1)))
            elif color_by == 'kind':
                col = KIND_COLOURS.get(kind, '#8a8f93')
                legend[kind] = col
            elif color_by == 'line':
                col = PAIR_COLOURS[l % 2]
            elif color_by == 'paragraph':
                col = PAIR_COLOURS[para_of[l] % len(PAIR_COLOURS)]
            else:
                col = '#2875a8'
            corners = to_plot([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
            ax.add_patch(Polygon(corners, closed=True, facecolor=col if img is None else 'none', edgecolor=col, alpha=0.35 if img is None else 0.9, linewidth=0.6))
            if labels:
                c = corners.mean(0)
                ax.text(c[0], c[1], drawn['words'][i], fontsize=5, ha='center', va='center', color='#222222', rotation=_word_rotation(L, i - L['start'], word_direction), rotation_mode='anchor')
    if 'baselines' in show:
        pts = _baseline_points(drawn, ms, baseline)
        for l, L in lines:
            P = [pts[i] for i in range(L['start'], L['end']) if pts[i] is not None]
            if not P:
                continue
            P = sorted({(q[0], q[1]) for q in P})
            Q = to_plot([[x, y] for x, y in P])
            ax.plot(Q[:, 0], Q[:, 1], '-', color='#b8371f', linewidth=0.8, alpha=0.9, marker='.', markersize=2.5, label='baselines (%s)' % baseline if l == lines[0][0] else None)
    if 'orientation' in show:
        for l, L in lines:
            o = L['orientation']
            bs = [geom[i] for i in range(L['start'], L['end']) if geom[i]]
            if not bs:
                continue
            if o['kind'] == 'rotated' and o.get('angle_deg') is not None:
                c = np.array([np.mean([(b[0] + b[2]) / 2 for b in bs]), np.mean([(b[1] + b[3]) / 2 for b in bs])])
                th = math.radians(o['angle_deg'])
                d = np.array([math.cos(th), math.sin(th)]) * 60.0
                a0, a1 = to_plot([c - d])[0], to_plot([c + d])[0]
                ax.annotate('', xy=a1, xytext=a0, arrowprops=dict(arrowstyle='->', color=KIND_COLOURS['rotated'], lw=1.2))
            elif o['kind'] == 'circular' and o.get('centre') and o.get('radius'):
                cx, cy = o['centre']
                ring = to_plot([[cx + o['radius'] * math.cos(a), cy + o['radius'] * math.sin(a)] for a in np.linspace(0, 2 * math.pi, 181)])
                ax.plot(ring[:, 0], ring[:, 1], ':', color=KIND_COLOURS['circular'], linewidth=0.8)
                cc = to_plot([[cx, cy]])[0]
                ax.plot(cc[0], cc[1], '+', color=KIND_COLOURS['circular'], markersize=8)
    if 'breaks' in show:
        from .geometry import line_breaks
        br = line_breaks(drawn, ms)
        for l, L in lines:
            for r in br[l]:
                if r['transcript'] and r['gap'] and r['left'] is not None and r['right'] is not None:
                    y = (geom[r['left']][3] + geom[r['right']][3]) / 2
                    seg = to_plot([[r['gap'][0], y], [r['gap'][1], y]])
                    ax.plot(seg[:, 0], seg[:, 1], '-', color='#c56939', linewidth=2.2, alpha=0.8)
    if legend:
        from matplotlib.patches import Patch
        _legend_below(ax, [Patch(facecolor=c, label=k) for k, c in legend.items()], ncol=min(6, len(legend)))
    elif 'baselines' in show and ax.get_legend_handles_labels()[0]:
        _legend_below(ax)
    state = ('%s frame, recorded warp (converted from flat for the image)' % t['frame']) if converted else '%s frame, %s warp' % (tags(drawn)['frame'], tags(drawn)['warp'])
    title = '%s · %s\n%s · on the %s image' % (folio, state, drawn.get('policy') or 'bundle', image) if image else '%s · %s\n%s · data %s' % (folio, state, drawn.get('policy') or 'bundle', data_version())
    if measure_name:
        title += ' · ' + measure_name
    if img is not None:
        return _finish(ax, title, (0, img.shape[1]), (img.shape[0], 0), invert=False)
    return _finish(ax, title, (min(xs) - pad, max(xs) + pad), (min(ys) - pad, max(ys) + pad))


def _compare_data(data, coordinates: str, baseline: str):
    if data is not None:
        return data
    from . import compare as C
    key = ('compare', baseline)
    if key not in _LOADED:
        _LOADED[key] = C.prepare(_bundle(None, 'recorded', 'sensitivity'), _ms(), baseline=baseline)
    return _LOADED[key]


def _draw_selection(ax, sel, colour, labels=False, alpha=1.0, context=True):
    from matplotlib.patches import Rectangle
    for u in sel['all']:
        r = u['rect']
        if not u['selected'] and not context:
            continue
        a = alpha if u['selected'] else 0.12
        ec = colour
        ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], facecolor=colour, edgecolor=ec, alpha=a * 0.25, linewidth=0.8))
        ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fill=False, edgecolor=ec, alpha=a, linewidth=0.8, linestyle='--' if u['anchor'] else '-'))
        if labels and u['selected']:
            ax.text((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, u['text'], fontsize=5, ha='center', va='center', color=colour, alpha=a)


def _fmt(v):
    return '-' if v is None else '%.3f' % v


def plot_pair(pair, ax=None, mode: str = 'overlay', labels: bool = True, shade: bool = True, drift: bool = False, drift_gain: float = 1.0):
    """Draw a ``compare.PairComparison`` (two selections in one frame): overlay with the shared area shaded, or two
    panels side by side; optionally the pages' pre-correction drift guides through the origin.

    Args:
        pair: a PairComparison (``compare.Comparison.pages``).
        ax: an Axes (overlay) or two Axes (side).
        mode: 'overlay' or 'side'.
        labels: write the words.
        shade: shade the intersections (overlay).
        drift: draw each page's drift guide (``compare.page_drift``) through the comparison origin, slope x `drift_gain`.

    Returns:
        the Axes or the two Axes; the title carries the scores and the frame and warp state.
    """
    from . import compare as C
    plt = _plt()
    a, b, m = pair.a, pair.b, pair.scores()
    rects = [u['rect'] for s in (a, b) for u in s['all'] if u['selected']] or [[-100, -100, 100, 100]]
    xlim = (min(r[0] for r in rects) - 30, max(r[2] for r in rects) + 30)
    ylim = (min(r[1] for r in rects) - 30, max(r[3] for r in rects) + 30)
    title = '%s %s vs %s %s · top %s lines · align %s · %s frame, %s warp\nDice %s · direct-overlap EVA %s · nearby EVA %s · %d / %d scored boxes · data %s' % (
        a['folio'], a['block']['key'], b['folio'], b['block']['key'], a['cutoff'], a['alignment'], a['frame'], a['warp'], _fmt(m['dice']), _fmt(m['local_segment_similarity']), _fmt(m['nearby_similarity']), m['units_a'], m['units_b'], data_version())
    guides = []
    if drift:
        for k, s in enumerate((a, b)):
            d = C.page_drift(pair.data, s['folio'], s['coordinates'])
            g = C.drift_guide(d, drift_gain, xlim[0], xlim[1])
            guides.append((k, d, g))
    if mode == 'side':
        from matplotlib.patches import Patch
        if ax is None:
            ratio = (ylim[1] - ylim[0]) / max(1.0, xlim[1] - xlim[0])
            fig, axes = plt.subplots(1, 2, figsize=(13, min(9.0, max(3.6, 6.2 * ratio + 2.4))), sharex=True, sharey=True)   # two equal-aspect panels plus title and legend
            axes = list(axes)
        else:
            axes = list(ax)
        handles = []
        for k, (s, axk) in enumerate(zip((a, b), axes)):
            _draw_selection(axk, s, PAIR_COLOURS[k], labels)
            handles.append(Patch(facecolor=PAIR_COLOURS[k], alpha=0.5, label='%s %s' % (s['folio'], s['block']['key'])))
            for kk, d, g in guides:
                if kk == k and g:
                    line, = axk.plot([g[0][0], g[1][0]], [g[0][1], g[1][1]], '-' if k == 0 else '--', color=PAIR_COLOURS[k], linewidth=1.5)
                    line.set_label('%s drift %+.2f deg, n=%d (%s state%s)' % (s['folio'], d['angle'], d['n'], d['coordinates'], '' if drift_gain == 1 else ', slope x%g' % drift_gain))
                    handles.append(line)
            axk.set_title('%s %s' % (s['folio'], s['block']['key']), fontsize=9, loc='left')
            axk.set_xlim(*xlim)
            axk.set_ylim(*ylim)
            if axk.get_ylim()[0] < axk.get_ylim()[1]:
                axk.invert_yaxis()
            axk.set_aspect('equal')
            axk.set_xlabel('x (px)')
            axk.set_ylabel('y (px)')
        _legend_below(axes[0], handles, ncol=min(4, len(handles)))
        fig = axes[0].figure
        fig.suptitle(title, fontsize=9, x=0.02, ha='left')
        _margins(fig, title)
        return axes
    ax = _axes(ax, xlim[1] - xlim[0], ylim[1] - ylim[0], size=9.0, min_height=4.5)
    for k, s in enumerate((a, b)):
        _draw_selection(ax, s, PAIR_COLOURS[k], labels)
    if shade:
        from matplotlib.patches import Rectangle
        for x in a['chosen']:
            for y in b['chosen']:
                if pair.same_row and x['line'] != y['line']:
                    continue
                r = C.intersection(x['rect'], y['rect'])
                if r:
                    ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], facecolor='#39886e', alpha=0.3, edgecolor='none'))
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=PAIR_COLOURS[0], alpha=0.5, label=a['folio']), Patch(facecolor=PAIR_COLOURS[1], alpha=0.5, label=b['folio']), Patch(facecolor='#39886e', alpha=0.5, label='shared area')]
    for k, d, g in guides:
        if g:
            line, = ax.plot([g[0][0], g[1][0]], [g[0][1], g[1][1]], '-' if k == 0 else '--', color=PAIR_COLOURS[k], linewidth=1.5)
            line.set_label('%s drift %+.2f deg, n=%d (%s state%s)' % ((a, b)[k]['folio'], d['angle'], d['n'], d['coordinates'], '' if drift_gain == 1 else ', slope x%g' % drift_gain))
            handles.append(line)
        elif d is not None:
            handles.append(Patch(facecolor='none', edgecolor='none', label='%s drift unavailable: %s' % ((a, b)[k]['folio'], d.get('unavailable'))))
    _legend_below(ax, handles, ncol=min(3, len(handles)))
    return _finish(ax, title, xlim, ylim)


def plot_composite(composite, ax=None, labels: bool = False):
    """Draw a ``compare.Composite``: every selection in one frame, one colour per page."""
    plt = _plt()
    sels = composite.selections
    rects = [u['rect'] for s in sels for u in s['all'] if u['selected']] or [[-100, -100, 100, 100]]
    xlim = (min(r[0] for r in rects) - 30, max(r[2] for r in rects) + 30)
    ylim = (min(r[1] for r in rects) - 30, max(r[3] for r in rects) + 30)
    ax = _axes(ax, xlim[1] - xlim[0], ylim[1] - ylim[0], size=9.0, min_height=4.5)
    from matplotlib.patches import Patch
    for k, s in enumerate(sels):
        _draw_selection(ax, s, PAIR_COLOURS[k % len(PAIR_COLOURS)], labels, alpha=0.6, context=False)
    _legend_below(ax, [Patch(facecolor=PAIR_COLOURS[k % len(PAIR_COLOURS)], alpha=0.5, label='%s %s' % (s['folio'], s['block']['key'])) for k, s in enumerate(sels)], ncol=min(4, len(sels)))
    s = sels[0]
    return _finish(ax, '%d blocks · align %s · cutoff %s · %s frame, %s warp · data %s' % (len(sels), s['alignment'], s['cutoff'], s['frame'], s['warp'], data_version()), xlim, ylim)


def plot_comparison(folio_a: str, folio_b: str, mode: str = 'overlay', cutoff=None, align: str = 'starts', coordinates: str = 'flat', block_a: str = 'opening',
                    block_b: str = 'opening', scale: str = 'pixels', ax=None, data=None, labels: bool = True, baseline: str = 'auto', shade: bool = True, drift: bool = False):
    """Two pages' blocks laid over each other (or side by side), with the overlay scores.

    Args:
        folio_a, folio_b: the pages.
        mode: 'overlay' (both blocks in one frame, shared area shaded) or 'side' (two panels in one shared frame).
        cutoff: the top 1..5 lines of the blocks, or None / 'all' for the whole blocks.
        align: 'starts' (each block translated to its first box's anchor) or 'page' (each page translated to its
            opening anchor, so later paragraphs keep their page positions).
        coordinates: 'flat' or 'recorded'.
        block_a, block_b: 'opening' | 'page' | 'p1'.. (``compare.page_blocks``).
        scale: 'pixels' or 'body_height'.
        ax: an Axes for mode 'overlay', or a pair of Axes for mode 'side'.
        data: ``compare.prepare`` data (loaded with the default bundle when None).
        labels: write the words.
        baseline: the anchor method.
        shade: shade the intersections in overlay mode.

    Returns:
        the Axes (mode 'overlay') or the list of two Axes (mode 'side'); the title carries the Dice, direct-overlap
        and nearby EVA similarity and the scored box counts, the legend names the pages.

    Example:
        >>> ax = plot_comparison('f20v', 'f21r', cutoff=3)      # doctest: +SKIP
    """
    from . import compare as C
    data = _compare_data(data, coordinates, baseline)
    cutoff = 'all' if cutoff in (None, 'all') else int(cutoff)
    pair = C.PairComparison(data, C.select(data, folio_a, block_a, cutoff, coordinates, align, scale), C.select(data, folio_b, block_b, cutoff, coordinates, align, scale))
    return plot_pair(pair, ax=ax, mode=mode, labels=labels, shade=shade, drift=drift)


def plot_wheel(folio: str, wheel=None, ax=None, bundle=None, labels: bool = True, policy: str = 'sensitivity', word_direction: str = 'ring'):
    """One page's wheels in the recorded frame: the rectangles of the accepted rings, each ring's fitted circle, the
    wheel centre, and the rejected circular loci dotted.

    Args:
        folio: the page.
        wheel: a wheel id ('f68r2/wheel1') or 1-based index to draw one wheel only; None draws all.
        ax: an Axes.
        bundle: the bundle whose rectangles are drawn (default the manuscript bundle in the recorded state).
        labels: write the words.
        word_direction: 'ring' (default) writes each word with its bottom towards the wheel's centre, 'level' upright.

    Returns:
        the Axes; the title names the wheels drawn and the frame.

    Example:
        >>> plot_wheel('f68r2')          # doctest: +SKIP
    """
    from .wheels import wheels_for, page_wheels
    from .frames import tags
    from .orientation import attach
    from matplotlib.patches import Rectangle, Circle
    _check_direction(word_direction)
    ms = _ms()
    app = _bundle(bundle, 'recorded', policy)
    attach(app, ms)
    prod = wheels_for(app, ms)
    rec = page_wheels(folio, prod)
    wheels = rec['wheels']
    if wheel is not None:
        wheels = [w for k, w in enumerate(wheels) if w['id'] == wheel or k + 1 == wheel]
        if not wheels:
            raise KeyError('%s has no wheel %r' % (folio, wheel))
    geom = app['geometry']
    rects = [geom[a] for w in wheels for r in w['rings'] for a, b in r['tokens'] if geom[a]]
    for rj in rec['rejected']:
        L = app['lines'][rj['line']]
        rects += [geom[i] for i in range(L['start'], L['end']) if geom[i]]
    if not rects:
        ax = _axes(ax, 1000, 1000)
        ax.text(0.5, 0.5, '%s: no circular text' % folio, ha='center', va='center', transform=ax.transAxes)
        return _finish(ax, '%s · no wheels' % folio, (0, 1000), (0, 1000))
    xs = [r[0] for r in rects] + [r[2] for r in rects]
    ys = [r[1] for r in rects] + [r[3] for r in rects]
    ax = _axes(ax, max(xs) - min(xs) + 80, max(ys) - min(ys) + 80)
    for k, w in enumerate(wheels):
        col = PAIR_COLOURS[k % len(PAIR_COLOURS)]
        for r in w['rings']:
            ax.add_patch(Circle(r['centre'], r['radius'], fill=False, edgecolor=col, linestyle=':', linewidth=0.8))
            for a, b in r['tokens']:
                g = geom[a]
                if not g:
                    continue
                ax.add_patch(Rectangle((g[0], g[1]), g[2] - g[0], g[3] - g[1], facecolor=col, edgecolor=col, alpha=0.3, linewidth=0.6))
                if labels:
                    L = app['lines'][r['line']]
                    ax.text((g[0] + g[2]) / 2, (g[1] + g[3]) / 2, ' '.join(app['words'][a:b + 1]), fontsize=5, ha='center', va='center', color='#222222',
                            rotation=_word_rotation(L, a - L['start'], word_direction), rotation_mode='anchor')
        ax.plot(w['centre'][0], w['centre'][1], '+', color=col, markersize=12, markeredgewidth=1.5, label='%s · r %.0f · %d rings · %d boxes' % (w['id'], w['radius'], len(w['rings']), w['words']))
    for rj in rec['rejected']:
        L = app['lines'][rj['line']]
        for i in range(L['start'], L['end']):
            g = geom[i]
            if g:
                ax.add_patch(Rectangle((g[0], g[1]), g[2] - g[0], g[3] - g[1], fill=False, edgecolor='#8a8f93', linestyle='--', linewidth=0.6))
        ax.plot([], [], '--', color='#8a8f93', label='rejected locus %s: %s' % (rj['locus'], rj['reason']))
    _legend_below(ax, fontsize=6)
    t = tags(app)
    return _finish(ax, '%s · %d wheel(s) · %s frame, %s warp\nwheels %s · data %s' % (folio, len(wheels), rec.get('frame', t['frame']), t['warp'], prod.get('version'), data_version()),
                   (min(xs) - 40, max(xs) + 40), (min(ys) - 40, max(ys) + 40))


def plot_centered_wheels(pages, ax=None, bundle=None, labels: bool = False, policy: str = 'sensitivity', nearby_labels: bool = False, word_direction: str = 'ring'):
    """The wheels of one page or several pages translated to a common centre (``wheels.centered_layout``): the display
    transform of the comparison workspace, in the frame 'display'. No scaling, no rotation: ring radii and local
    deviations stay visible, the coincident centre is imposed by the display and is no evidence of a shared template.

    Args:
        pages: a folio or a list of folios.
        ax: an Axes.
        bundle: the bundle (default the manuscript bundle in the recorded state).
        labels: write the words.
        nearby_labels: include each wheel's nearby non-paragraph units.
        word_direction: 'ring' (default) writes each word with its bottom towards the centre, 'level' upright.

    Returns:
        the Axes; the title says 'display frame'.

    Example:
        >>> plot_centered_wheels('fRos')          # doctest: +SKIP
    """
    from .wheels import centered_layout, extent
    from .orientation import attach
    from matplotlib.patches import Rectangle, Circle
    _check_direction(word_direction)
    ms = _ms()
    app = _bundle(bundle, 'recorded', policy)
    attach(app, ms)
    folios = [pages] if isinstance(pages, str) else list(pages)
    lay = centered_layout(app, ms, pages=folios, labels=nearby_labels)
    half = extent(lay)
    ax = _axes(ax, 2 * half, 2 * half)
    for k, w in enumerate(lay['wheels']):
        col = PAIR_COLOURS[k % len(PAIR_COLOURS)]
        cx, cy = w['centre']
        for r in w['rings']:
            ax.add_patch(Circle((r['centre'][0] - cx, r['centre'][1] - cy), r['radius'], fill=False, edgecolor=col, linestyle=':', linewidth=0.6, alpha=0.7))
        for u in w['words']:
            r = u['rect']
            ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], facecolor=col if u['kind'] == 'circular' else 'none', edgecolor=col, alpha=0.3 if u['kind'] == 'circular' else 0.8, linewidth=0.6))
            if labels:
                L = app['lines'][u['line']]
                ax.text((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, u['text'], fontsize=4.5, ha='center', va='center', color=col, rotation=_word_rotation(L, u['first'] - L['start'], word_direction), rotation_mode='anchor')
        ax.plot([], [], color=col, label='%s · r %.0f' % (w['id'], w['radius']))
    ax.plot(0, 0, '+', color='#222222', markersize=10)
    _legend_below(ax, ncol=3 if len(lay['wheels']) > 6 else min(3, max(1, len(lay['wheels']))), fontsize=6)
    return _finish(ax, '%s · %d wheels translated to a common centre\ndisplay frame (not measured geometry) · %s warp · data %s' % (', '.join(folios), len(lay['wheels']), lay['warp'], data_version()),
                   (-half, half), (-half, half))


def plot_bifolium(bifolium: str, face: str = 'inner', axes=None, bundle=None, warp: str = 'flat', show: Sequence[str] = ('boxes', 'baselines'), policy: str = 'sensitivity', **kw):
    """The two pages of a bifolium face side by side as they lie on the opened sheet: inner = A verso | B recto,
    outer = B verso | A recto (``manuscript.load_physical``).

    Args:
        bifolium: the node id ('C:20-21').
        face: 'inner' or 'outer'.
        axes: two Axes (a new figure when None).
        bundle, warp, show, policy: as ``plot_page``; other keywords pass to ``plot_page``.

    Returns:
        the list of two Axes (a missing slot gets an empty panel saying so).

    Example:
        >>> plot_bifolium('C:20-21', 'inner')          # doctest: +SKIP
    """
    from .compare import face_slots
    plt = _plt()
    ms = _ms()
    slots = face_slots(face)
    pages_of = {}
    for p in ms.pages:
        if p['node'] == bifolium:
            pages_of.setdefault(('A' if p['leaf'] == p['A'] else 'B') + p['side'], []).append(p['folio'])
    if not pages_of:
        raise KeyError('no bifolium %r' % bifolium)
    if axes is None:
        fig, axes = plt.subplots(1, 2, figsize=(12, 7.5))
    axes = list(axes)
    for slot, ax in zip(slots, axes):
        folios = pages_of.get(slot, [])
        if len(folios) == 1:
            plot_page(folios[0], ax=ax, bundle=bundle, warp=warp, show=show, policy=policy, **kw)
        else:
            ax.text(0.5, 0.5, '%s %s: %s' % (bifolium, slot, 'no page' if not folios else 'several panels (%s): choose one with plot_page' % ', '.join(folios)), ha='center', va='center', transform=ax.transAxes, fontsize=8)
            ax.set_title('%s %s' % (bifolium, slot), fontsize=9, loc='left')
    axes[0].figure.suptitle('%s · %s face (%s) · data %s' % (bifolium, face, ' | '.join(slots), data_version()), fontsize=10, x=0.02, ha='left')
    return axes


def main(argv=None):
    """``vmsspatial plot <folio> --out file.png [--image display|beinecke] [--compare <folio>] [--wheel] [--centered] [--bifolium <node> --face inner|outer]``"""
    import argparse
    ap = argparse.ArgumentParser(prog='vmsspatial plot', description='Print a page, a comparison, a wheel or a bifolium face to a PNG (matplotlib, Agg).')
    ap.add_argument('folio', help="the page ('f75r'), or the bifolium id with --bifolium")
    ap.add_argument('--out', required=True, help='the PNG (or any matplotlib format) to write')
    ap.add_argument('--image', choices=('display', 'beinecke'), help='draw the page image from the cache under the rectangles (recorded coordinates)')
    ap.add_argument('--warp', default='flat', choices=('flat', 'recorded'))
    ap.add_argument('--policy', default='sensitivity', choices=('strict', 'sensitivity'))
    ap.add_argument('--compare', metavar='FOLIO', help='overlay this page on the first (compare.select / measure)')
    ap.add_argument('--cutoff', default=None, help='top lines of the compared blocks (1..5 or all)')
    ap.add_argument('--align', default='starts', choices=('starts', 'page'))
    ap.add_argument('--mode', default='overlay', choices=('overlay', 'side'))
    ap.add_argument('--drift', action='store_true', help="draw each page's pre-correction drift guide through the origin (compare.page_drift)")
    ap.add_argument('--wheel', action='store_true', help="the page's wheels in the recorded frame")
    ap.add_argument('--centered', action='store_true', help="the page's wheels translated to a common centre (display frame)")
    ap.add_argument('--bifolium', action='store_true', help='the first argument is a bifolium id; draw a face')
    ap.add_argument('--face', default='inner', choices=('inner', 'outer'))
    ap.add_argument('--labels', action='store_true', help='write the words')
    ap.add_argument('--word-direction', default='ring', choices=WORD_DIRECTIONS, help='ring: along the writing, a ring word\'s bottom towards the centre; level: every word upright')
    ap.add_argument('--color-by', default=None, help='kind, line, paragraph, or a key of line_stats.KEYS')
    ap.add_argument('--show', default='boxes,baselines', help='comma list of boxes, baselines, orientation, breaks')
    ap.add_argument('--dpi', type=int, default=150)
    args = ap.parse_args(argv)
    show = tuple(s for s in args.show.split(',') if s)
    if args.compare:
        cutoff = None if args.cutoff in (None, 'all') else int(args.cutoff)
        ax = plot_comparison(args.folio, args.compare, mode=args.mode, cutoff=cutoff, align=args.align, coordinates=args.warp, labels=args.labels, drift=args.drift)
        fig = (ax[0] if isinstance(ax, (list, tuple)) or hasattr(ax, 'shape') else ax).figure
    elif args.wheel:
        fig = plot_wheel(args.folio, labels=args.labels, policy=args.policy, word_direction=args.word_direction).figure
    elif args.centered:
        fig = plot_centered_wheels(args.folio, labels=args.labels, policy=args.policy, word_direction=args.word_direction).figure
    elif args.bifolium:
        fig = plot_bifolium(args.folio, args.face, warp=args.warp, show=show, policy=args.policy, labels=args.labels, color_by=args.color_by, word_direction=args.word_direction)[0].figure
    else:
        fig = plot_page(args.folio, warp=args.warp, show=show, color_by=args.color_by, labels=args.labels, image=args.image, policy=args.policy, word_direction=args.word_direction).figure
    fig.savefig(args.out, dpi=args.dpi)                        # margins were reserved by the plot functions; tight_layout would undo them
    print('wrote %s' % args.out)
    return 0
