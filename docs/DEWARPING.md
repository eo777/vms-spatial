# Dewarping: removing the page warp

The word rectangles were drawn on photographs of a bound book. A page's lines share a curve and a tilt that are not
the scribe's, and in the recorded coordinates those mix with the scribe's own drift. Dewarping estimates what the lines
of a page share and subtracts it, leaving what each line does on its own. It corrects coordinates, not pixels: no image
is changed, and only vertical positions move.

## The method

The toolkit uses a **robust, leave-one-line-out polynomial warp model with per-line fixed effects**. That is a
description, not an established name: the method was built for this toolkit from standard parts. If you cite it,
describe the parts below.

For a page, with x and y scaled to u and v, each running from -1 to 1 across the text block:

```
y = a_l + b_l u + W(u, v_l)
W(u, v) = sum for k = 2..3 of (w_k0 + w_k1 v) u^k
```

Each line l has its own intercept a_l and slope b_l. The field W is one smooth surface shared by all the lines of the
page. Because each line's straight part belongs to the line, W can only hold curvature that lines at the same
horizontal position have in common.

## The steps

1. **Baseline points.** One point per located, non-oversized rectangle on the page's horizontal lines; a shared rectangle
   counts once. By default (`baseline='auto'`) the point comes from the ink baseline where the page has clean ink
   records and from the glyph-corrected box baseline otherwise.
2. **Fit the shared curve.** Each line's intercept and slope are projected out of the data and of the curve's terms, then
   the terms are fitted by least squares. Huber weights down-weight outlying words.
3. **Fit tilt and keystone.** A robust straight line `s(v) = c0 + c1 v` through the fitted line slopes, weighted by each
   line's point count. `c0` is the page tilt, and `c1` the keystone: how the tilt changes from the top of the page to the bottom.
4. **Leave each line out.** The curve applied to a line comes from a fit without that line, so a line that really bows
   is not flattened by its own data. That curve is read only across the range the other lines cover, and held at its
   edge value beyond that, never extrapolated.
5. **Subtract.** `shift = W(u, v_l) + s(v_l) u`, minus the page's mean shift so that the page does not move as a whole, and
   `y_flat = y - shift`. A box's top and bottom move together, so its width and height do not change.

## The named parts

| Part | Used for |
|---|---|
| Fixed effects | one intercept and one slope per line, as in a panel regression with lines as the groups |
| Frisch-Waugh-Lovell projection | removes the line effects before the curve is fitted |
| Bivariate polynomial surface | the shared curve: cubic across the page, varying linearly down it |
| Huber M-estimation by iteratively reweighted least squares | down-weights outlying words |
| Leave-one-out estimation (cross-fitting) | keeps a line's own shape out of its own correction |

## Parameters

| Parameter | Value | Effect |
|---|---|---|
| `degree` | 3 | highest power of u in the curve |
| `min_words` | 3 | located rectangles a line needs in order to count as usable |
| `min_lines` | 4 | usable lines a page needs; below this it stays as recorded |
| `FEW_LINES` | 8 | below this many usable lines, the terms that vary down the page are dropped, from both curve and tilt |
| `HUBER_C` | 1.345 | Huber tuning constant |
| `MAD_SCALE` | 1.4826 | residual scale: this times the median absolute deviation |
| `IRLS_ITERATIONS` | 5 | reweighting passes |

## Using it

The fit is stored once, in `data/manuscript/page_warp.json.gz`. Use the stored fit, and do not fit your own in an analysis.

```python
from vmsspatial import load_bundle, warp

flat = load_bundle('strict')                       # the default state: the warp is removed
recorded = load_bundle('strict', warp='recorded')  # as drawn on the photographs
warp.page_status('f75r')                           # whether this page has a fitted field
warp.transform(flat, 'recorded')                   # move a tagged table to the other state
```

`vmsspatial.flatten.flatten` is the fitter behind that product, and `python -m vmsspatial build-products` rebuilds it.
`tests/test_flatten.py` recovers a synthetic page with a known warp, tilt and keystone to within 2 px.

## What it cannot tell you

- **Slant and camera rotation look the same.** A slant the scribe held across a whole page cannot be told from camera
  rotation, so both are removed. A line's deviation from the page's shared slope survives.
- **The curvature has no identified cause.** Binding would bend the gutter side of a page most, but the stronger side of
  the fitted curve falls on the gutter side on about half of the pages, which is chance. Call it shared page curvature,
  not binding.
- **Shared drift goes with the warp.** If the scribe bowed every line of a page alike, that bow is removed as well.
- **Only horizontal text is fitted or moved.** Rotated, circular and radial lines keep their recorded positions, because
  a field fitted on horizontal text cannot be checked on them.
- **Flat coordinates do not sit on the photograph.** Anything drawn on a page image must be in recorded coordinates.

## Relation to other work

The closest published family is text-line-based document dewarping, which estimates page shape from the curves of the
text lines. Those methods usually assume a physical page surface and re-render the image. This one assumes no physical
surface, corrects coordinates only, and separates each line's own drift from the shared warp, because that drift is what
is being measured. We have not surveyed that literature, so a closer precedent may exist.
