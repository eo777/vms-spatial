# The Page stream page

`viewer/stream.html` shows whole pages in a chosen order: a chain of bifolia with four pages to a row, one continuous column,
or laid over each other. Use it to look along a sequence of sheets: restore each page's recorded tilt, set how far each
bifolium overlaps the one before, and see whether margins and angles carry from sheet to sheet. It is a display: it fits
nothing and scores nothing. The geometry is in `viewer/js/stream_math.js`, tested in `viewer/test/stream_math.test.js`, and
it reads the same compare data as the Compare page.

## Controls

| Control | Address | What it does |
|---|---|---|
| Group; Group by, under Settings | `group` (all is the default), `by` = section (golf is the default) | the whole manuscript, a Golf group or a section. No page is held back: every group is on the list, 5a, 6 and quire N included |
| Order | `order` = path1, herbal_a_1a, herbal_a_1a_folds (bifolia is the default) | Manuscript by bifolium; proposed Path 1; or the ten-sheet Herbal A candidate with shared / separate folds |
| Arrangement | `view` = stream, overlay (chain is the default) | Bifolium chain, Continuous column, Superimposed overlay |
| Columns | `columns` = faces (singulion is the default) | chain: singulion Ar Av Br Bv, or the physical faces Bv Ar and Av Br |
| Joins | `join` = half, frames (touch is the default) | chain: rows that meet with no gap, a 50% default overlap, or separate fixed frames with page headers |
| Covered area | `covered` = outline, margin, hidden, full (faint is the default) | what is drawn of an older row below the fold. It changes no geometry |
| Page positions | `route` = slot:Ar and so on, cycle:Ar and so on (all is the default) | column and overlay: all four positions, one position on each bifolium, or the candidate correspondence Ar → Bv → Br → Ar, Av → Av |
| Trail, Earlier pages | `trail` = pair, single (all is the default), `fade` | overlay: accumulate pages, previous and current, or current only, and how faint earlier pages are |
| Align | `anchor` = opening, margin (source is the default) | Source x keeps the page's x from its source image, Opening word puts the first word at x = 0, Median body margin puts the median left edge of the body rows at x = 0. One horizontal translation a page |
| Tilt | `tilt` = turn, none (restore is the default) | see below |
| Words, Margin points | `words=0`, `margins=0` | EVA in the boxes; the left end of each complete body row, joined only across consecutive rows |
| Zoom | `zoom` = 0.5, 0.75, 1.5, 2, 3 | a share of the available width; Fit is the default |
| Coordinates, Scale, under Settings | `coords` = recorded, `scale` = pixels, paper | flat (dewarped) or recorded (as drawn) coordinates; body height scales each page in both directions alike to a common median word height; Parchment draws every page in millimetres from its fold and its leaf's top edge (below), and Align then has no part |
| Bifolium, ⇤ ← → ⇥, slider, `[` `]`, page chips | `at`, a page index | navigation. In a column or chain the page scrolls and every page stays present |
| Adjust overlaps; a ↕ label in the plot | `overlaps` = `A:1-8>F:42-47=0.333\|…`, `seam`, `strength` | drag a label, or use the arrow keys on it (1%, 5% with Shift, Home, End), or the boundary menu and exact percentage, 0 to 95% of the preceding row's text height. That row and all later rows move, and nothing else. A value belongs to a directed pair of neighbours, so another order cannot carry it to different neighbours |
| Separate Ar / Av+Br / Bv folds, under Adjust overlaps | `foldMode` = separate (shared is the default); `foldPart` = Ar, inner, Bv; `folds` = `A:1-8>D:27-30@Ar=0.7\|…` | optional independent vertical placements for Ar, tied Av+Br, and Bv. Column handles edit one group and its successors. A missing group value falls back to that pair's shared overlap. Switching off preserves the separate values and restores shared positions |
| Reorder bifolia | `custom`, the full list of bifolia | drag a row, use ↑ ↓, or Alt + ↑ ↓ on the grip. Pages and panels stay with their sheet and colours stay with their sheets. It applies only to the same set of sheets. Reset order returns to the chosen order, and a pair that recurs gets its overlap back |
| Saved boundaries | none | named sets in this browser, with Download JSON and Import JSON as the portable copy. Import checks every value and keeps only known settings |
| Export JSON, under Settings | none | every page's angles, transform, margin rows before and after the tilt, plot position, and every boundary |
| A list of pages | `pages` = f1r,f2r | shows those pages. The chain shows their whole bifolia |

Links and boundary files from the comparison workspace of the 2026 bifolium drift study open here too, with their order, joins and
overlaps. That workspace turned its pages rigidly, which leans every margin, so they open on the recorded tilt instead and the page
says so. Rigid turn under Tilt shows how one looked there. An address that names `tilt=turn` keeps it, with a warning at the top of the page.

## Herbal A · 1a candidate

Two Order presets use the full ten-bifolium configuration:

**A:1-8 → D:27-30 → F:42-47 → G:49-56 → A:2-7 → D:25-32 → C:20-21 → E:35-38 → A:4-5 → D:28-29**.

**1a · original single joins** (`#order=herbal_a_1a`) loads the original one-fold overlap values, with separate folds off.
**1a · separate folds** (`#order=herbal_a_1a_folds`) loads the same order with Ar / shared Av+Br / Bv fits enabled.
The seven-sheet middle run is the main copying-target chain; the other three joins provide context and have weaker fits.
All four mapped pages of each sheet are included (40 pages). Selecting either preset clears prior page/group filters and
manual reordering, and opens a singulion chain in recorded coordinates, with source x retained and no added rotation.
Physical-face columns remain available. Reset order returns to this chain. Links and saved boundary sets retain the
fold mode and both shared and separate overlap maps, including explicit resets and zero-overlap edits.

The small `js/stream_1a_preset.js` bundle is generated from the saved copying-window metrics by
`research/bifolium_drift_20261030/build_public_1a_preset.py` in the research workspace; it includes source hashes.
This release does not rerun the fits. The presets use saved opening anchors and H for the 39 originally observed pages,
and saved sheet extents, whenever coordinates are recorded and scale is body height. Those reproduce the study's
registered rectangle positions and preserve the fit percentages' denominator. They use current recorded boxes, whose
extents match that snapshot. f49v is now visible, lies within the saved sheet extents, and retains its current registration;
it was unscored in the original study. The tied inner fold for either join touching it comes from Br alone.
Current ink/glyph baseline angles are still displayed; they are not the historical angle inputs of the saved score.
Other coordinate/scale settings leave the study registration, with a note. The saved scores remain references, not new fits.

Separate folds retain independent cumulative vertical positions, one per group. Av and Br are tied even in physical-face
column order. Covered text is clipped or faded at its own group's next boundary. No x fitting or extra rotation is added.
The overlap drawer shows the saved mismatch and chosen constant-score interval; other near alternatives are recorded in
the data bundle. Ranges describe score tolerances, not confidence intervals. Changing a fold does not rescore the fit.

## Parchment scale

Under the other scales, the space across a fold is not to scale. Every column spans the text of every page in the view,
each page keeps the x of its own photograph, and body height sizes each page by its handwriting. **Parchment** (`scale=paper`)
draws each page in millimetres on its leaf instead. x is measured from the fold, so in physical faces the two pages of a face
meet at the dashed line between them, and y from the leaf's top edge, which the two pages of a face share. A column is one
leaf, 160 mm, the catalogue's width.

The fold and the edges are measured on the Beinecke scans (`vmsspatial.leaves`, the data product
`data/manuscript/leaves.json.gz`). Each scan shows its page in the binding on a black ground, at one resolution:

- **Fold.** Walking out from the text toward the binding, the first long straight edge of at least 30% of that band's strongest,
  then the strongest within the next 8 mm. The leaf often curves into the gutter as a soft band before its edge. The edge where the
  visible leaf meets the binding stands for the fold. Any strip of the leaf hidden in the binding is not measured, so a gap across
  a fold can only be short of the truth, by that strip.
- **Top and bottom.** The long straight edge nearest the text above it and below it.
- **Edge score.** The 35th percentile of the gradient across a candidate line along the whole span of the text, at the best angle
  within 1.5° of the axis, so a drawing crossing the band does not make an edge.
- **Scale.** Set once for all scans: the median height of the 176 ordinary leaves (3,564 scan px) is the catalogue's 225 mm, which
  gives 15.84 px per mm. A leaf taller or shorter than that keeps its own size. The scans' edges reach the recorded frame through the
  stored registration.

Checks on the result:

- Ordinary leaves measure 221 to 232 mm tall (5th to 95th percentile). Their visible width, fold to fore-edge, has a median of 157 mm.
  The catalogue gives 160. The width is rough: the fore-edge is the first line past the text, which can be the edge of the stack, and
  versos read a median 12 mm wider than rectos (`visible_width_mm` in the product, left out where it lies more than 20% from 160 mm).
- Rectos and versos share one scale: median word height 4.40 mm on rectos and 4.38 mm on versos. The two sides of one leaf differ in
  height by a median of 3.8 mm, with no consistent sign. Read that as the noise of one top or bottom edge, about 2 to 3 mm.
- On a by-eye audit of 16 pages, 12 of them random, the fold lay on the visible edge to within 1 to 2 mm.
- 197 folds and 221 top edges are measured. An ordinary leaf's median inner margin, fold to text, is 14.2 mm.

A value that is missing or implausible is estimated, and the note under the figure names those pages:

- **Fold.** A foldout panel away from the binding, and f71v, take the crease or fold placed on the scan (`fold_method` 'sheet',
  docs/SHEETS.md). The median inner margin serves a faint edge (f99v).
- **Top edge.** First, where the edges nearest the text are not a leaf's height apart, the strongest pair of edges that is. This
  happens when the text is a band across the middle of the page, as on f101r, so that the nearest edges are drawings. Otherwise a
  foldout panel takes the top edge of the panel beside it on the same scan (f90r2, f102r2), since one piece of parchment runs
  across the crease. Failing both, the bottom edge less 225 mm, or the median top margin. Each was checked by eye on its scan
  (2026-11-04).
- **Scale.** Scan 1006203 (f71v and f72r) was photographed at another distance and has its own scale, from its leaves' height. f101v's
  display image shows only its first panel, so its registration is fitted on the words of that panel alone (`images.display_transform` leaves
  out the words clipped off the image) and holds the rest of the page in the same frame. fRos is drawn in its own quarter-size scan, so its scale comes from the scan's.

Foldout pages wider than a leaf are cut at the column edge, and the note names them too. Rows are still placed by the extent of the
text. The overlaps of a saved chain were set under body height, so on this scale they no longer line the text up as they did.

Both coordinate states lie on the parchment. **Recorded** draws the words as they were drawn on the photographs. **Flat** draws
them dewarped (docs/DEWARPING.md), which moves words up and down only and leaves the page where it was. Tilt puts the page angle
back about the mean centre of the page's own words, so it does not lift the page off its leaf. Over every page, a dewarped page's
mean word sits within 0.42 mm of its recorded place (95th percentile), and within 0.8 mm at worst (f101v, f8r). Each word moves a
median of 0.46 mm with the tilt taken out, and 0.27 mm with it put back.

## Tilt

The independent [f1r/f8r MSI audit](MSI_LEAF_AUDIT.md) checks the catalogue-scaled parchment frame against photographed rulers and visible front-leaf edges. It finds approximately 3 mm less bottom margin on both pages and a direction-dependent scale discrepancy on f8r. Its compact data are preserved separately; the scalar parchment view above has not been silently recalibrated.

A flat page has lost its overall tilt along with its warp. The side labels and page headers give each page's **recorded tilt**:
the median signed first-to-last baseline angle of its qualifying lines (at least 4 located boxes spanning at least 3 median
word widths, `compare.page_drift`), positive falling to the right. It is the slope of the text lines, not of the left margin.

Flattening moves words **up and down only**: every x is the x that was recorded. So there are two different ways to put a
tilt back, and they do not give the same page.

- **Recorded tilt, x unchanged** (the default) undoes the tilt the way flattening removed it: y + kx, with
  k = tan(recorded) − tan(current). This is one adjustment for the whole page: the page's median line angle comes back and every x
  stays as recorded. Each line keeps its flat shape, so it does not get back its own recorded angle: over 3,773 lines on 202 pages it
  stays a median of 0.37° from that angle, 90% within 1.26°. The rest of the warp stays out.
- **Rigid turn** rotates the page by recorded minus current angle. Word sizes and distances hold exactly, but a rotation moves
  x as well, which flattening never did. So each drawn margin leans by the page's own turn, on top of its slope.

Measured on the 183 pages with at least 6 margin rows and an angle, as slopes of the drawn margin, in degrees:

| Against the margin in recorded coordinates | Median difference | 90% within |
|---|---:|---:|
| Flat, nothing restored | 0.016 | 0.10 |
| Recorded tilt, x unchanged | 0.012 | 0.10 |
| Rigid turn | 1.10 | 2.60 |
| Rigid turn, after taking the page's turn off | 0.015 | 0.11 |

The last row is the cause: under a rigid turn, drawn margin = recorded margin − turn. f30v's margin is 5.48° and draws at 9.67°.
The left rail of f8v's first paragraph is 4.15° in recorded coordinates, 4.09° with the default and 7.29° with the rigid turn.
Between neighbouring bifolia in Path 1, the median difference of the bifolium's median margin slope is 0.95° on the recorded margins,
0.97° with the default, and 1.86° with the rigid turn. **Compare margins only under the default, or in recorded coordinates**, which
already hold the tilt: Tilt is switched off there, because no setting moves anything.

## Reading it carefully

- **A join is a choice.** Rows are placed by the extent of the text, not by the edge of the paper. A boundary you set by hand is
  where you put it, and that the text then lines up is what you were looking for, not evidence that it does.
- **Shared joins move whole rows.** With separate folds enabled, Ar, tied Av+Br and Bv advance independently. Within each
  group the page origins stay fixed. Source images share no vertical origin, so even under Source x heights are opening-relative.
- **The tilt depends on the baseline.** This data reads baselines from ink where a page has clean ink records and from
  glyph-corrected boxes elsewhere (`baseline`, `auto`: 193 and 34 pages). Anchored on glyph-corrected boxes alone, page angles differ
  by a median of 0.13° and at most 1.28° (f45r, −0.18° against +1.10°), and 6 of 202 pages change sign. Say which baseline a number used
  (`docs/PITFALLS.md` 16), and treat a pattern that lives within that spread as unsettled.
- **A margin here is the edge of the text, not of the parchment.** Its angles are from the vertical of the coordinate frame, and the opening
  baseline sets each page's vertical origin. Only the Parchment scale measures from the parchment: the fold and the top edge, estimated
  as above. Nothing measures the curve of the vellum.
- **A margin is not always a margin.** The margin trace follows the left end of complete body rows. Where the text wraps a drawing,
  as on f101v, f46v or f36v, it wanders hundreds of pixels sideways, and a slope fitted to it is not a page edge.
- **Pages with no angle keep their flat tilt.** The note under the figure names them, and the pages with no box on their opening
  line (fRos, f116v), which cannot be placed.

## Origin

The method comes from the Page stream of the 2026 bifolium drift study. This page runs it on the toolkit's corrected data,
so f49v, which that view could not place, is drawn here. It differs in four other ways. The default tilt keeps the recorded margin, as
above. Tilt reads the toolkit's baselines, not glyph anchors alone. No group is held back. The study's frozen coordinate modes and
saved stability orders are left out, along with its line reader in the overlay.
