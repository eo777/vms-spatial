# Printing pages with matplotlib

`vmsspatial.plot` draws a page, a comparison, a wheel, the centred wheels of a page and a bifolium face, for when
the web atlas is not at hand. It needs matplotlib (`pip install vms-spatial[plot]`), uses the Agg backend (no
display needed), returns the Axes and leaves saving to the caller. Every title names the frame and the warp state
of what is drawn and the data version; nothing drawn on a page image is in the flat state.

```
python -m vmsspatial plot f75r --out f75r.png                      # the page in the flat state, boxes and baselines
python -m vmsspatial plot f75r --out f75r.png --image display      # on the Voynichese display image (recorded coordinates)
python -m vmsspatial plot f20v --compare f21r --cutoff 3 --out pair.png [--drift] [--mode side]
python -m vmsspatial plot f68r2 --wheel --out wheel.png
python -m vmsspatial plot fRos --centered --out rosettes.png
python -m vmsspatial plot C:20-21 --bifolium --face inner --out face.png
```

## A page

```python
from vmsspatial import plot
ax = plot.plot_page('f75r')                                        # flat state, sensitivity geometry, baselines 'auto'
ax.figure.savefig('f75r.png', dpi=150)
ax = plot.plot_page('f75r', warp='recorded', color_by='paragraph', labels=True)
ax = plot.plot_page('f68r2', show=('boxes', 'orientation'), color_by='kind')   # arrows along rotated lines, the circle of each ring
ax = plot.plot_page('f75r', show=('boxes', 'breaks'))                           # the transcript intrusion breaks
ax = plot.plot_page('f75r', image='display')                                    # the page image from the cache under the boxes
ax = plot.plot_page('f75r', image='beinecke', show=('boxes',))                  # the Beinecke scan (downloaded on first use)
```

`show` takes any of `boxes`, `baselines`, `orientation`, `breaks`. `color_by` is None, `'kind'` (the line's
orientation kind, with a legend), `'line'`, `'paragraph'`, a key of `line_stats.KEYS` (below) or a sequence of
per-token values painted on a colour scale. With `labels=True` a word follows its line's direction, a ring word's bottom
towards the centre; `word_direction='level'` stands every word upright (`plot_page`, `plot_wheel`,
`plot_centered_wheels`, `--word-direction`; the rule is `orientation.label_angle`, the atlas's own). With `image`, a flat bundle is converted to recorded coordinates first (the title says so) and the geometry is
mapped through the stored registration (`vmsspatial.images`), so the rectangles sit on the photograph; the page image
is read from the image cache outside the repository (`vmsspatial fetch-images`). Without an image the flat state is
drawn by default, y downward as on the page.

## Line statistics

`vmsspatial.line_stats` gives the numbers behind the atlas's Colors group "Lines, baselines and warp": one record per
horizontal line and one per located rectangle, as `compare.Records` with `to_csv`. Any key of `line_stats.KEYS` paints a
page, on the atlas's scale.

```python
from statistics import median
from vmsspatial import line_stats, plot
lines = line_stats.line_table()                                    # one record per horizontal line, every page
words = line_stats.word_table()                                    # one record per located rectangle
lines.to_csv('lines.csv'); words.to_csv('words.csv')
study = [r for r in lines if r['n_anchors'] >= 4 and (r['span_W'] or 0) >= 3 and r['chord_flat'] is not None]   # name your own rule
median_angle = median(abs(r['chord_flat']) for r in study)
print(len(study), 'lines, median |chord angle|', round(median_angle, 2), 'deg flat')
ax = plot.plot_page('f75r', color_by='resid_chord', show=('boxes',))   # each word against its line's chord
ax.figure.savefig('f75r_residuals.png', dpi=150)
```

No qualification rule is applied: a chord needs two anchors, a least-squares fit three, a shape measure four, and a line
reports None for what it cannot support. `H` is the page's median box height and y runs down the page. An angle is
positive falling to the right, a residual below the line, `sag` when the middle lies lower on the page than the ends.
`sag` is -c / 4 for the quadratic term c of y/H = a + b u + c u^2 (u = 0..1 along the line, column `quad_c`), so a
negative c is a sag. The other signs, the columns' states and the units are in the module's docstring and in `KEYS`.

## A comparison

```python
ax = plot.plot_comparison('f20v', 'f21r', cutoff=3)                 # overlay: the two openings, shared area shaded
axes = plot.plot_comparison('f20v', 'f21r', cutoff=3, mode='side')  # two panels in one frame
ax = plot.plot_comparison('f7r', 'f32r', align='page', block_a='p2', block_b='p1', coordinates='recorded')
```

The title carries the occupied-area Dice, the direct-overlap and nearby EVA similarity and the scored box counts
(docs/COMPARE.md); the legend names the pages; the anchor boxes are grey. `data=` passes prepared comparison data
(`compare.prepare`) so that several figures share one load. From the object API: `pair = compare.Comparison().pages('f20v',
'f21r', cutoff=3); pair.plot()` (which is `plot.plot_pair(pair)`), `plot.plot_pair(pair, drift=True, drift_gain=5)` adds each
page's pre-correction drift guide through the origin (solid A, dashed B, the angle and line count in the legend), and
`compare.Comparison().composite([...]).plot()` (`plot.plot_composite`) draws several pages in one frame.

## Wheels

```python
ax = plot.plot_wheel('f68r2')                                       # both wheels: ring rectangles, fitted circles, centres; rejected loci dashed
ax = plot.plot_wheel('f70r2', wheel=1)                              # one wheel by index or id ('f70r2/wheel1')
ax = plot.plot_centered_wheels('fRos')                              # the nine wheels translated to a common centre
ax = plot.plot_centered_wheels(['f71r', 'f72r1', 'f72r2', 'f72r3'], nearby_labels=True)
```

`plot_wheel` draws in the recorded frame. `plot_centered_wheels` draws the display transform of
`wheels.centered_layout` and says 'display frame' in its title: the coincident centre is imposed, not measured
(docs/WHEELS.md).

## A bifolium face

```python
axes = plot.plot_bifolium('C:20-21', 'inner')                       # A verso | B recto, as the opened sheet lies
axes = plot.plot_bifolium('C:20-21', 'outer', warp='recorded', show=('boxes',))
```

Keyword arguments pass to `plot_page`. A slot with several foldout panels is left empty with a note naming them.

## Tests

`tests/test_plot.py` renders every figure into a buffer and checks the artists (one polygon per unit, one baseline
polyline per line, the circles of circular lines, the legend and the title's frame and warp words);
`tests/test_line_stats.py` runs the example above. No PNG is committed; `outputs/` is ignored by git and the publisher.
