# Wheels: the circles of the circular text

The manuscript's circular text (the zodiac pages, the astronomical and cosmological diagrams, the Rosettes) is
recorded as rectangles like any other word. `vmsspatial.wheels` fits, per circular locus, the circle its word
rectangles lie on, screens the fit, groups coincident rings into wheels and ships the result as the data product
`data/manuscript/wheels.json.gz`. The orientation records take their centres from it (`vmsspatial.orientation`).

## The fit

The centre of a ring is fitted from the centres of its DISTINCT recorded rectangles (a rectangle shared by several
tokens counts once) by algebraic least squares, solved after centring the points (`wheels.fit_circle`; the same
estimator as `orientation.circle_fit`, numerically stable for large coordinates). The fit returns the centre, the
radius, the radial RMS residual, the arc the points cover (360 degrees minus the largest angular gap) and the number
of points.

## Acceptance

A ring is accepted when, with H the page's body box height (the median height of the recorded rectangles on its
paragraph lines; all its rectangles when it has none),

| screen | threshold |
|---|---|
| distinct located boxes | at least 5 |
| arc covered | at least 180 degrees |
| radius | at least 2 H |
| radial RMS residual | at most 1 H and at most 12 percent of the radius |

A rejected ring keeps its locus, its reason and its fit for inspection; nothing is inferred for it. The reasons are
the sentences in `wheels.REASONS`.

## Grouping

Accepted rings are taken from the most to the least populated. A ring joins the first group every member of which
has its centre within max(H, 8 percent of the smaller of the two radii) of the ring's centre (complete linkage, so a
chain of displaced circles cannot merge distinct wheels). A wheel's centre is the coordinate-wise median of its rings'
centres, its radius the largest ring radius, and `centre_spread` the largest distance of a ring centre from the
wheel centre. Separate centres on a page stay separate.

## The product

```python
from vmsspatial import wheels
prod = wheels.load_wheels()                       # data/manuscript/wheels.json.gz
prod['summary']                                   # 35 wheels on 26 pages, 4 rejected circular loci, 2,216 accepted boxes
w = prod['pages']['f68r2']['wheels'][0]           # id, centre, radius, centre_spread, rings (locus, centre, radius, residual, arc_deg, n, tokens), words, labels
wheels.wheels_table()                             # flat rows for a CSV
```

Per page: `H`, `W`, `wheels`, `rejected` (`locus`, `reason`, `fit`), `circular_lines`, `frame` (recorded; `detected` for
the Rosettes, whose boxes were found on the toolkit's image). A ring's `tokens` are places in its line, so the product
holds for any stream; `wheels.wheels_for(app)` gives a bundle's own line and token indices. The product is tagged recorded /
recorded / voynichese; circular lines are not moved by the page warp, so the fit is the same in both warp states.
`python -m vmsspatial build-products wheels` rebuilds it (`wheels.build`), `wheels.fit_wheels(app, ms)` fits any
bundle.

Counts on the manuscript (sensitivity geometry, every page): 27 pages have circular loci; 26 carry 35 wheels
(all 12 Zodiac pages one each; six wheels on five Astronomical pages; f68r2 two centres, the Rosettes nine); 4
circular loci are rejected, each with fewer than five distinct boxes (f68r1's four-box locus among them); 2,216 word
boxes belong to accepted rings.
Pages with radial labels and no circular locus (f67r2, f67v1) get no centre.

## Orientation records

For a circular line the orientation record's `centre` is the WHEEL centre its ring belongs to, `radius` the ring's
own fitted radius, `wheel` the wheel id, `circle` the ring's own fit diagnostics; `word_angles` are the tangent
angles about the wheel centre. A rejected ring keeps `kind: circular` with `centre: None`, `rejected: <reason>` and
confidence 0.2. A radial line takes the nearest accepted wheel of its page (`centre`, `radius` of the wheel); a page
without an accepted wheel gives its radial lines no centre ('circle:none (no accepted wheel on the page)' in the
basis). Before 2026-10-31 every circular line, rejected or not, carried its own fitted centre and radial lines the
median of all fits of the page.

Word labels read their direction from these records (`viewer/js/word_labels.js`, used by the atlas and the comparison page). `word_angles` on a
circular line puts each word's bottom towards the wheel's centre: 0 degrees at 12 o'clock, 90 at 3, 180 at 6, -90 at 9, clockwise on the page. The
rings run clockwise, so words at 6 o'clock read upside down, as they are written. A label is sized by the word's length along that direction, because
an axis-aligned box says nothing about a word running down the page: the boxes at 3 and 9 o'clock are narrow, and fitting their width gives about half
the size. The Word direction control swaps this for Level, the same words upright at the same size, to read them without turning your head. Only the
labels turn. A ring that failed the screens has no `word_angles`, so its words are drawn level.

## The display transform

```python
lay = wheels.centered_layout(app, ms, 'fRos')                  # every wheel translated to (0, 0)
lay = wheels.centered_layout(app, ms, pages=['f71r', 'f72r1', 'f72r2'], labels=True)
```

Each wheel is translated so that its centre lies at the origin. Nothing else changes: no scaling, no rotation, no
radius normalisation, no word rearrangement. Ring radii and local deviations stay visible. The result is tagged
`frame: 'display'`, a frame of its own in `vmsspatial.frames`: `require_same` refuses to combine it with measured
geometry, `require_recorded` refuses to draw it on a page image. `wheels.extent` gives the half-frame that holds
every centred rectangle (650 px over all accepted wheels with their nearby labels). `plot.plot_centered_wheels`
draws it; the viewer's `compare/wheels.json.gz` carries the fits for the atlas.

A coincident centre after this transform is imposed by the display. It is not evidence of a shared template or a
common instrument (PITFALLS 24).

## Limits

- The fit reads the recorded rectangles, which were drawn on a photograph of a bound book; a wheel centre is a
  property of the drawing, not of the ink. The circular lines are not flattened (the page warp is fitted on
  horizontal text), so their coordinates carry the photograph's warp in both states.
- A ring whose words are not all located (the Rosettes' detected boxes carry a confidence) is fitted on what is
  located; the arc screen protects against a short located stretch, not against a missing half that happens to be
  symmetric.
- The screens are display screens, chosen so that a drawn circle follows the text. They are not a test that the
  text was written on a compass-drawn circle; the residuals are there to look at.
- Nearby labels (non-paragraph units within radius + H of a wheel centre) are listed with the nearest wheel for
  display; a label is never guessed into a wheel's text.
