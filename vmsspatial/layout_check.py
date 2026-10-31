"""Does a rearranged or synthetic text keep the page's geometry? (the typesetting check of 28 October 2026)

For a line-aligned text with its geometry: words that did not fit their slot and were carried on, words without a box,
boxes that overlap another box of the same page (intersection over the smaller box above 0.2), and the recorded box
width over the word's own width at the line's letter size (median |log ratio| and the share off by 1.5x). Renders
chosen pages (f75r and f33v by default, the trickiest Bio layouts) for inspection.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


def overlaps(geometry, line_words, ms, threshold=0.2) -> int:
    starts = np.cumsum([0] + [len(ws) for ws in line_words])
    total = 0
    for p in ms.pages:
        idx = [i for l in range(p['start_line'], p['end_line']) for i in range(starts[l], starts[l + 1]) if geometry[i]]
        if len(idx) < 2:
            continue
        b = np.array([geometry[i] for i in idx], float)
        x0 = np.maximum(b[:, None, 0], b[None, :, 0])
        y0 = np.maximum(b[:, None, 1], b[None, :, 1])
        x1 = np.minimum(b[:, None, 2], b[None, :, 2])
        y1 = np.minimum(b[:, None, 3], b[None, :, 3])
        inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
        area = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
        smaller = np.minimum(area[:, None], area[None, :])
        ratio = np.where(smaller > 0, inter / np.maximum(smaller, 1e-9), 0)
        total += int((np.triu(ratio, 1) > threshold).sum())
    return total


def width_error(ms, frames, line_words, geometry) -> dict:
    """Box width over the word's width at the line's letter size: median |log ratio|, share off by 1.5x, boxed words."""
    ratios = []
    i = 0
    for l, ws in enumerate(line_words):
        fr = frames[l]
        cw = sum(b - a for a, b in fr[4]) / max(ms.lines[l]['chars'], 1) if fr else None
        for w in ws:
            g = geometry[i]
            i += 1
            if g and cw and len(w):
                ratios.append((g[2] - g[0]) / (len(w) * cw))
    r = np.log(np.array(ratios))
    return dict(median_abslog=float(np.median(np.abs(r))), off_1p5=float((np.abs(r) > np.log(1.5)).mean()), boxed=len(ratios))


def check(ms, frames, line_words, geometry, carried=0, moved=None) -> dict:
    return dict(carried=int(carried), no_box=int(sum(1 for g in geometry if not g)), overlaps=overlaps(geometry, line_words, ms), moved=moved,
                width=width_error(ms, frames, line_words, geometry))


def letter_size_change(cw_ratio) -> Optional[dict]:
    if cw_ratio is None:
        return None
    r = np.log(np.asarray(cw_ratio))
    return dict(median_abslog=float(np.median(np.abs(r))), beyond_1p5=float((np.abs(r) > np.log(1.5)).mean()), beyond_2=float((np.abs(r) > np.log(2)).mean()))


def draw_page(ax, ms, folio, line_words, geometry, frames, title, fontsize=4.2):
    """Render one page's boxes and words into a matplotlib axis (frames in grey, boxes in blue)."""
    from matplotlib.patches import Rectangle
    starts = np.cumsum([0] + [len(ws) for ws in line_words])
    p = ms.page(folio)
    xs, ys = [], []
    for l in range(p['start_line'], p['end_line']):
        fr = frames[l]
        if fr:
            for a, b in fr[4]:
                ax.plot([a, b], [fr[1], fr[1]], color='#dddddd', linewidth=0.6)
        for i in range(starts[l], starts[l + 1]):
            g = geometry[i]
            if not g:
                continue
            ax.add_patch(Rectangle((g[0], g[1]), g[2] - g[0], g[3] - g[1], facecolor='none', edgecolor='#4477aa', linewidth=0.5))
            ax.text((g[0] + g[2]) / 2, (g[1] + g[3]) / 2, line_words[l][i - starts[l]], ha='center', va='center', fontsize=fontsize, color='#222222')
            xs += [g[0], g[2]]
            ys += [g[1], g[3]]
    if xs:
        ax.set_xlim(min(xs) - 20, max(xs) + 20)
        ax.set_ylim(max(ys) + 20, min(ys) - 20)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=8, loc='left')


def render_pages(ms, frames, panels: List[tuple], folio: str, path, cols=2, pw=10.0, dpi=160):
    """panels: [(name, line_words, geometry)]; writes a PNG of the page under every panel."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    first = panels[0]
    starts = np.cumsum([0] + [len(ws) for ws in first[1]])
    p = ms.page(folio)
    boxes = [first[2][i] for l in range(p['start_line'], p['end_line']) for i in range(starts[l], starts[l + 1]) if first[2][i]]
    w = max(b[2] for b in boxes) - min(b[0] for b in boxes)
    h = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    rows = int(np.ceil(len(panels) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * pw, rows * (pw * h / w + 0.5)))
    axes = np.atleast_1d(axes).ravel()
    for ax, (name, lines, geom) in zip(axes, panels):
        draw_page(ax, ms, folio, lines, geom, frames, '%s: %s' % (folio, name))
    for ax in axes[len(panels):]:
        ax.axis('off')
    fig.suptitle('%s: every rearrangement re-typeset into the recorded line frames (grey: frame segments; blue: word boxes)' % folio, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
