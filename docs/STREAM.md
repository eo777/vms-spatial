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
| Order | `order` = path1 (bifolia is the default) | Manuscript by bifolium, or Path 1, a proposed glyph-statistical ordering and not an established chronology |
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
| Coordinates, Scale, under Settings | `coords` = recorded, `scale` = pixels | flat or recorded coordinates; body height scales each page in both directions alike to a common median word height |
| Bifolium, ⇤ ← → ⇥, slider, `[` `]`, page chips | `at`, a page index | navigation. In a column or chain the page scrolls and every page stays present |
| Adjust overlaps; a ↕ label in the plot | `overlaps` = `A:1-8>F:42-47=0.333\|…`, `seam`, `strength` | drag a label, or use the arrow keys on it (1%, 5% with Shift, Home, End), or the boundary menu and exact percentage, 0 to 95% of the preceding row's text height. That row and all later rows move, and nothing else. A value belongs to a directed pair of neighbours, so another order cannot carry it to different neighbours |
| Reorder bifolia | `custom`, the full list of bifolia | drag a row, use ↑ ↓, or Alt + ↑ ↓ on the grip. Pages and panels stay with their sheet and colours stay with their sheets. It applies only to the same set of sheets. Reset order returns to the chosen order, and a pair that recurs gets its overlap back |
| Saved boundaries | none | named sets in this browser, with Download JSON and Import JSON as the portable copy. Import checks every value and keeps only known settings |
| Export JSON, under Settings | none | every page's angles, transform, margin rows before and after the tilt, plot position, and every boundary |
| A list of pages | `pages` = f1r,f2r | shows those pages. The chain shows their whole bifolia |

Links and boundary files from the comparison workspace of the 2026 bifolium drift study open here too. They open on the
rigid turn they were made with, so that they look as they did.

## Tilt

A flat page has lost its overall tilt along with its warp. The side labels and page headers give each page's **recorded tilt**:
the median signed first-to-last baseline angle of its qualifying lines (at least 4 located boxes spanning at least 3 median
word widths, `compare.page_drift`), positive falling to the right.

Flattening moves words **up and down only**: every x is the x that was recorded. So there are two different ways to put a
tilt back, and they do not give the same page.

- **Recorded, true margins** (the default) undoes the tilt the way flattening removed it: y + kx, with
  k = tan(recorded) − tan(current). Lines return to their recorded angle, every x stays as recorded, and only the local warp
  stays out.
- **Rigid turn** rotates the page by recorded minus current angle. Word sizes and distances hold exactly, but a rotation moves
  x as well, which flattening never did. So each drawn margin leans by the page's own turn, on top of its true slope.

Measured on the 183 pages with at least 6 margin rows and an angle, as slopes of the drawn margin, in degrees:

| Against the margin in recorded coordinates | Median difference | 90% within |
|---|---:|---:|
| Flat, nothing restored | 0.016 | 0.10 |
| Recorded, true margins | 0.012 | 0.10 |
| Rigid turn | 1.10 | 2.60 |
| Rigid turn, after taking the page's turn off | 0.015 | 0.11 |

The last row is the cause: under a rigid turn, drawn margin = true margin − turn. f30v's margin is 5.48° and draws at 9.67°.
Between neighbouring bifolia in Path 1, the median difference of the bifolium's median margin slope is 0.95° on the true margins,
0.97° with the default, and 1.86° with the rigid turn. **Compare margins only under the default, or in recorded coordinates.**

## Reading it carefully

- **A join is a choice.** Rows are placed by the extent of the text, not by the edge of the paper. A boundary you set by hand is
  where you put it, and that the text then lines up is what you were looking for, not evidence that it does.
- **Only whole rows move.** The pages of a bifolium keep their relative heights from their opening baselines, whichever is
  shorter. The source images share no vertical origin, so even under Source x the heights are opening-relative.
- **The tilt depends on the baseline.** This data reads baselines from ink where a page has clean ink records and from
  glyph-corrected boxes elsewhere (`baseline`, `auto`: 193 and 34 pages). Anchored on glyph-corrected boxes alone, page angles differ
  by a median of 0.13° and at most 1.28° (f45r, −0.18° against +1.10°), and 6 of 202 pages change sign. Say which baseline a number used
  (`docs/PITFALLS.md` 16), and treat a pattern that lives within that spread as unsettled.
- **A margin is not always a margin.** The margin trace follows the left end of complete body rows. Where the text wraps a drawing,
  as on f101v, f46v or f36v, it wanders hundreds of pixels sideways, and a slope fitted to it is not a page edge.
- **Pages with no angle keep their flat tilt.** The note under the figure names them, and the pages with no box on their opening
  line (fRos, f116v), which cannot be placed.

## Origin

The method comes from the Page stream of the 2026 bifolium drift study. This page runs it on the toolkit's corrected data,
so f49v, which that view could not place, is drawn here. It differs in four other ways. The default tilt keeps the true margin, as
above. Tilt reads the toolkit's baselines, not glyph anchors alone. No group is held back. The study's frozen coordinate modes and
saved stability orders are left out, along with its line reader in the overlay.
