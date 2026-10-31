# The Sections page

`viewer/sections.html` lays every page of a section or Golf group over each other, so you can see what the pages of a
group share: where the text sits, how the paragraphs are shaped, and where the paragraphs start and end. It is a display:
it fits nothing, scores nothing, and moves pages by translation only. The geometry is in `viewer/js/section_math.js`, tested
in `viewer/test/section_math.test.js`, and it reads the same compare data as the Compare page.

## Controls

| Control | Address | What it does |
|---|---|---|
| Group by, Group, ‹ › | `by` = golf (section is the default), `group` | a section or Golf group, or All groups as panels on one shared frame. Pages run in manuscript order |
| Align | `align` = starts (page is the default) | Page positions keeps each page's layout on one anchor. All paragraph starts moves every paragraph to its own anchor |
| Anchor | `anchor` = top-left, bottom-left (opening is the default) | the opening word's baseline, or a corner of the complete horizontal text |
| Colour by | `color` = bifolium, group, section (page is the default) | one colour per page, or shared across a bifolium, Golf group or section. Geometry does not change |
| Heatmap, Paragraph polygons, Word boxes, Breaks, Paragraph starts, Paragraph ends | `layers`, comma separated, `none` for no layers | which layers are drawn |
| Opacity sliders | `op`, seven percentages in the order of the sliders | one 0 to 100% slider per layer, with paragraph fill and outlines separate. A slider changes no geometry and redraws nothing |
| Heatmap cell, Heatmap colours | `cell` = 10, 40, 80 (20 is the default), `palette` = gray, amber | the grid size in display units, and three ten-band colour scales. On a dark page the scale reverses, so more pages is always brighter |
| Coordinates, Scale | `coords` = recorded, `scale` = body_height | flat or recorded coordinates; source pixels, or each page scaled to a common median word height |
| An outline or a Page colours chip; Escape | `focus` = a folio | picks one page out and dims the rest. The heatmap does not change |
| Wheel, drag, Fit, + − | none | zoom and pan, shared by the panels and kept across groups |

## What each layer means

**Paragraph polygons.** The outer envelope of a paragraph's complete horizontal lines, joined halfway across the whitespace
between them, so the boundary is stepped. It holds the located text and the gaps inside it: it is not an ink contour or an
illustration mask. A missing or rotated line, a reversed step, or a step over 2.5 line pitches starts a new polygon. A line is
complete when every one of its tokens is located.

**Heatmap.** For each cell, the share of the group's selected pages with at least one horizontal word box overlapping it.
A page votes once however many boxes it has there. The grid stays anchored at (0, 0) whatever the zoom. A page that could not
be aligned stays in the total and adds no boxes, so a share is never inflated by leaving a page out. The ten bands are the same
for every group, so groups can be compared. A box is not ink, and larger cells bridge small gaps.

**Breaks.** The transcription's annotated intrusions, drawn between two located words on a horizontal line. Ordinary word
spaces are not breaks.

**Paragraph starts and ends.** The first and last line of a paragraph, with a triangle at the start and a square at the end.
Only complete horizontal lines are drawn: a missing endpoint is counted, never replaced by a later line.

## Reading it carefully

- Pages or paragraphs meet at the anchor by construction. That convergence is not evidence of a shared template.
- Marks are not normalised by group size, so a larger group looks denser. The heatmap is the comparable layer.
- Only horizontal lines are drawn. Rings and rays are in Compare's Wheels view, so the Zodiac group shows little here.
- Pages without a usable anchor are named under the figure. In this data, 225 of 227 pages align on their opening word, and 710
  of 736 paragraphs align under All paragraph starts.

## Origin

The method comes from the Section layout view of the 2026 bifolium drift study. This page runs it on the toolkit's corrected
data. It leaves out that view's gap areas and gap matching, page-by-page membership editing, JSON export and wheel panels.
