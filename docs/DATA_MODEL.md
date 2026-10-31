# The spatial data model: frames, warp states, sources, products

Every number in this toolkit that is a position on a page belongs to a frame, a warp state and a source, and two
sets of positions may be combined only when they share the first two. This document says what the frames are, which
products are shipped in which state, what the tags guarantee and what they do not, and how to do the common things
in one call. The pitfalls these rules answer are PITFALLS 16 to 22.

## Defaults, and why

- `Manuscript.load()` = every page and every locus (227 pages, 5,365 lines, 38,876 tokens) by bifolium, each line
  with its locus type: the toolkit describes the recorded manuscript, not a study's subset. `order='folio'` is the true
  page sequence. The study subset is explicit: `Manuscript.load(pages='paragraph', order='path1')` (`manuscript.STUDY`).
- `load_bundle()` = the flat warp state: a vertical position in the recorded frame carries the photograph's warp (a
  writing-order effect once turned out to be half page sag), so the default removes it with the shipped product;
  `warp='recorded'` asks for the rectangles as drawn. Pages without a fitted field stay unchanged and say so
  (`warp.page_status(folio)`, the bundle's `warp_pages`). Overlays drawn on the page images need recorded
  coordinates: the tags enforce it and `viewer_data` converts explicitly.
- Baselines default to `'auto'`: ink where the page has clean ink records, the glyph-corrected box baseline
  elsewhere; the box bottom is a biased baseline (PITFALLS 17) and is never a default.
- Line statistics read horizontal lines (`orientations='horizontal'`) and report what they skipped; the other
  kinds are an explicit opt-in.
- A study names its own choices in full (PITFALLS 23); the toolkit's defaults are the public ones.

## Frames

| frame | what the coordinates are | pages |
|---|---|---|
| `recorded` | the pixel frame of the Voynichese Project's XML page (e.g. f75r is 1136 x 1500), the frame the word rectangles were recorded in | the 225 pages with recorded rectangles |
| `detected` | the pixel frame of the toolkit's quarter-scale copy of the Beinecke scan (`viewer/img/fRos.jpg`, named in `frame_image`), in which the Rosettes' boxes were detected | fRos (a bundle with fRos lists it in `detected_pages`) |
| `display` | coordinates moved for display only: `wheels.centered_layout` translates every wheel to a common centre. Not measured geometry: `require_same` refuses to combine it with anything, `require_recorded` refuses to draw it on an image | the centred wheel composites |

A page image is not a frame of the data: the Beinecke scan and the Voynichese display image are reached THROUGH the
registration (below) and every measurement made on them is returned in the recorded frame.

## Warp states

The rectangles were drawn on photographs of a bound book, so every line of a page carries the same shared curvature
at the same horizontal position, plus the camera's tilt and keystone (PITFALLS 16).

| warp | meaning |
|---|---|
| `recorded` | the photograph's page warp is still in the coordinates |
| `flat` | the page's shared warp has been removed with the stored page warp product (below): y_flat = y - shift(x, y, locus) |

The two states differ by up to a few box heights at the edges of a page. The flat state removes with the warp
whatever page-wide slant the scribe wrote (a constant slant cannot be told from camera rotation) and leaves each
line's own deviation from the page's shared slope and its own bowing. Rotated, circular and radial lines are not
fitted and are NOT moved: in a flat-state table they keep their recorded positions (the fit cannot be checked there).

The atlas computes its spatial measures in the flat state whichever way it draws. Its Coordinates control draws the
boxes and overlays in recorded coordinates (the default) or flat, from the bundle's `geometry_recorded` and `geometry`;
a shared box takes its review group's box against `sensitivityGeometry`, so the flat view needs no data of its own. A
page without a fitted field stays put, and the status line says so. With the page image on, the boxes and overlays go
back to recorded coordinates while the Flat choice stands, since the image is the photograph; unticking it returns to
Flat. An overlay item carries recorded `points` and `points_flat` beside them; `study_data` converts in both directions.
A bundle without `geometry_recorded` has one state to offer and the control is disabled.

## Sources

`source` says where the numbers were measured: `voynichese` (the recorded rectangles), `beinecke` (the Yale IIIF
scans), `display` (the Voynichese display image), `synthetic` (typeset by the toolkit from a line's frame), `detected`
(found on an image by `vmsspatial.segment`). Two tables with different sources but the same frame and warp MAY be
combined: that is what the registration is for.

## Tags on every table

Every coordinate-bearing dict carries `frame`, `warp`, `source` at top level: bundles (`load_bundle`, `make_bundle`,
`extend_bundle`, `flatten`, `warp.transform`), the baselines table, the ink product, the page warp and registration
products, and overlays written by `viewer_data`. A table without tags is read as recorded / recorded / voynichese,
the state every table was in before the tags existed, with a bundle's `geometry_kind` filling them in ('flattened'
gives warp flat, 'synthetic' source synthetic, 'detected' frame detected); `frames.ensure_tags` writes them.

```python
from vmsspatial import frames
frames.tags(table)                       # {'frame', 'warp', 'source', 'detected_pages', ...}
frames.require_same(a, b, 'the bundle and the ink product')   # FrameError naming both tags when frame or warp differ
frames.require_recorded(overlay, 'an overlay')               # drawn on the page image: recorded / recorded only
frames.describe(table)                   # 'recorded frame, flat warp, source voynichese'
```

`require_same` is called in every function that combines two coordinate sets: `SpatialContext`,
`geometry.line_frames` / `line_breaks`, `baselines.*`, `ink.baseline_points` / `intrusions` / `gap_table`,
`flatten.flatten`, `warp.transform`, `viewer_data.study_data`.

## Shipped products and their tags

| product | file | frame / warp / source | holds |
|---|---|---|---|
| manuscript bundle | `data/manuscript/words.json.gz` | recorded / recorded / voynichese (the file); `load_bundle()` returns recorded / flat | every page and locus by bifolium with the strict geometry and the review block, built from the review (`bundle.write_manuscript`, fRos in the detected frame); `load_bundle` swaps in the sensitivity geometry on request, applies the page warp and re-sequences it to any order or to the paragraph text; `pages='paragraph', order='path1', warp='recorded'` is the study shape |
| alignment review | `data/manuscript/spatial_review.json.gz` | recorded / recorded / voynichese | every ZL token's assignment group, flags, eligibility, and why a token has no usable box; `display_parts` are the same rectangles on the display image; built by `vmsspatial.realign` |
| registrations | `data/manuscript/registrations.json.gz` | recorded -> image pixels | per page and source (`beinecke`, `display`): the 3x3 matrix, the median reprojection error in recorded px, inlier counts, the quadratic residual field, the per-line local shift (keyed by locus), quality flags; `images.registration` reads it first |
| page warp | `data/manuscript/page_warp.json.gz` | applies to recorded / recorded; produces flat | per page the field basis and normalisation, full-fit coefficients, per-line leave-one-out coefficients and coverage interval (by locus), tilt line, reference shift, the baseline it was fitted on (ink or glyph), line kinds, quality; `warp.build` writes it |
| baselines table | `data/manuscript/baselines.json.gz` | recorded / recorded / voynichese | per token the box centre x and bottom and, per method (bottom, centre, glyph, ink), the baseline y and weight; `baselines.word_baselines` reads it, re-sequenced by (page, locus) for a bundle in another order with the same boxes (`baselines.table_for`) |
| ink measures | `data/manuscript/ink_measures.json.gz` | recorded / recorded / beinecke | per located rectangle of the sensitivity bundle the ink extent, angle, x-height band, ascender, descender, flags; per line the robust fit; per page the registration summary; records keyed by token id and (page, locus), `ink.for_bundle` moves them onto any stream |
| Rosettes supplement | `data/manuscript/supplement_fRos.json` | detected / recorded / detected | per token the detected box (full-resolution and display), method, confidence |
| coverage | `data/manuscript/coverage_by_page.csv` | (a table of counts) | per page and locus type: ZL tokens, XML words, bundle tokens, located strict / sensitivity, orientation kinds, detected, and the tokens without a usable box by reason (no XML word, transcriptions differ, position failed, invalid box, disconnected parts) |
| wheels | `data/manuscript/wheels.json.gz` | recorded / recorded / voynichese (fRos: detected) | per page the accepted wheels of the circular text (centre, radius, centre spread, rings with their fits and member tokens by locus and place in the line, nearby labels) and the rejected circular loci with reasons; `wheels.load_wheels`, built by `wheels.build`; `wheels.wheels_for` places them on a bundle in any order (docs/WHEELS.md). The orientation records take their centres from it |
| atlas line measures | `viewer/data/manuscript/words.json.gz` | recorded / flat, `geometry_recorded` beside it; overlays recorded with `points_flat` | the bundle's `measures`, `overlays`, `line_notes`, `line_note_fields`, `page_notes`, `anchors`: `vmsspatial.line_stats` on the sensitivity geometry, packaged by `viewer_measures`; ink values are measured on the Beinecke scan in the recorded frame |
| comparison extras | `viewer/data/compare/*.json.gz` | recorded / recorded (+ the flat shift per unit) | the atlas's comparison page data (`viewer_data.compare_data`): per page the units with recorded rectangles, flat shifts and baseline anchors, blocks, breaks, the drift indicator (per-line chord angles and the page median, recorded and flat); the wheels; the orders; the pair rankings (docs/COMPARE.md) |

Images are never shipped: the scans live in the image cache outside the repository (`images.cache_dir()`).

## Invariants

- A table in the flat state came from a recorded table through the stored page warp (its provenance names
  `page_warp_version` and the parent geometry's digest), never through a refit of its own.
- Two tables are combined only when `frames.require_same` passes: same frame, same warp state. The source may differ.
- The tags guarantee the frame and the state of the NUMBERS, not their accuracy: a `beinecke` value in the recorded
  frame is accurate to the registration's residual (median 0.8 recorded px, reported per page) plus the local
  residual field; two photographs do not share a warp beyond that field (PITFALLS 19). Report the residual beside
  an ink number.
- The page warp applies to horizontal lines; a rotated, circular or radial line keeps its recorded position in the
  flat state (`line_kinds` in the product says which).
- A detected box (fRos) is a position found on an image, with a confidence, in its own frame; it never enters a
  recorded-frame statistic silently (`detected_pages`, `require_same` on the frame).
- No product depends on the stream order: rows are keyed by page and locus or by token id, and a table stored in stream
  order is re-sequenced by those keys. A sheet is a label on pages and lines; nothing assumes its pages are adjacent.

## Orientation

Every line carries `orientation` (`vmsspatial.orientation`): `kind` (horizontal, rotated, circular, radial, label,
unknown), `angle_deg` (text direction, 0 = left to right, positive = clockwise, None for circular text), `centre` and
`radius` for circular and radial text with the per-word `word_angles`, `confidence`, `basis` (the cues: the ZL locus
type, the chord of the box centres with its span and residual, the boxes' aspect, the circle fit, the ink angle when
the optional `orientation.ink_pass` ran). The line statistics (`line_frames`, `line_units`, `line_breaks`,
`baselines`, `flatten`, `ink.measure_pages` / `intrusions` / `gap_table`) take `orientations='horizontal'` by default
and report what they skipped. `audit.flags.QUARANTINE` names the pages whose paragraph lines are not all horizontal,
`orientation.nonhorizontal_pages(load_bundle('sensitivity'))`.

## Recipes

Flatten a bundle (never refit it in a study):

```python
from vmsspatial import load_bundle
flat = load_bundle('sensitivity', warp='flat')          # or: from vmsspatial import warp; flat = warp.flatten_bundle(app)
flat['flatten']['pages']['f75r']                        # the stored fit's quality for the page (fitted, baseline, tilt, amplitude)
```

Move ink values, or any table, into the same state as the boxes you compare them with:

```python
from vmsspatial import warp
from vmsspatial.ink import load_ink, baseline_points
ink = load_ink()                                        # recorded / recorded / beinecke
flat_ink = warp.transform(ink, 'flat', app=app)         # every vertical value moved by its rectangle's shift, line fits redone
pts = baseline_points(flat_ink, flat)                   # OK: both flat. baseline_points(ink, flat) raises FrameError
y_flat = warp.apply('f75r', x, y, locus, 'flat')         # any y of a page, by its line's locus
```

Draw overlays on the page image (the viewer maps recorded coordinates onto the Voynichese image):

```python
from vmsspatial.frames import require_recorded
require_recorded(bundle, 'the bundle under the overlays')     # overlays follow the bundle's frame and warp
study_data(out, bundle, 'key', 'label', overlays={'fits': overlay('Fits', items)})
```

Study one kind of line on purpose:

```python
rings = load_bundle('sensitivity', extra=True)
from vmsspatial.orientation import line_mask
mask = line_mask(rings, 'circular')                      # the 80 circular loci; line_units(rings, ms, orientations='circular')
```

Compare two pages in one coordinate variant (`vmsspatial.compare`; the variants are the two warp states, the anchors
moved with the boxes; the 2026 workspace's own refit fields are study products and not here):

```python
from vmsspatial import compare as C
data = C.load()                                         # sensitivity geometry, both states derived, 'auto' anchors
a = C.select(data, 'f20v', cutoff=3, coordinates='flat')       # the stored page warp applied, anchors transported by each box's shift
b = C.select(data, 'f21r', cutoff=3, coordinates='recorded')   # the rectangles as drawn
C.measure(a, a)                                         # fine; C.measure(a, b) raises FrameError: flat against recorded
```

Rebuild the products after the review changes: `python -m vmsspatial build-products` (the manuscript bundle,
registrations from the cache, the baselines table, the page warp, the wheels, all on the default shape; the manifest
entries are updated), `python -m vmsspatial viewer-data` (the bundles, the layout and the comparison extras). Re-measure
the ink of the pages whose boxes changed with `ink.measure_pages` and `ink.replace_pages`, before the baselines table.

The October 2026 study shape:

```python
from vmsspatial import Manuscript, load_bundle
from vmsspatial.manuscript import STUDY            # {'pages': 'paragraph', 'order': 'path1'}
ms = Manuscript.load(**STUDY)
app = load_bundle('sensitivity', warp='recorded', **STUDY)   # the recorded rectangles the studies measured on
```
