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
| Anchor | `anchor` = opening, top-left, bottom-left (edge is the default) | Opening line, left edge takes its height from the opening word's baseline and its x from the leftmost box of the paragraph text. Opening word uses that word for both. The corners use a corner of the complete horizontal text, and need the first or last line to be complete and horizontal |
| Colour by | `color` = bifolium, group, section (page is the default) | one colour per page, or shared across a bifolium, Golf group or section. Geometry does not change |
| Heatmap, Paragraph polygons, Word boxes, Breaks, Paragraph starts, Paragraph ends | `layers`, comma separated, `none` for no layers | which layers are drawn |
| Opacity sliders | `op`, seven percentages in the order of the sliders | one 0 to 100% slider per layer, with paragraph fill and outlines separate. A slider changes no geometry and redraws nothing |
| Heatmap cell, Heatmap colours | `cell` = 10, 40, 80 (20 is the default), `palette` = gray, amber | the grid size in display units, and three ten-band colour scales. On a dark page the scale reverses, so more pages is always brighter |
| Coordinates, Scale | `coords` = recorded, `scale` = body_height | flat or recorded coordinates; source pixels, or each page scaled to a common median word height |
| Page colours, at the top; an outline or mark; Escape | `focus` = a colour's key: a folio, bifolium, Golf group or section | picks that colour out, so Colour by Bifolium picks out a whole bifolium. The other pages and the heatmap step back. A layer at 0% stays hidden, and the heatmap's counts do not change |
| Edit pages; the × beside a colour; Remove from view | `edits`, for example `section/Herbal A:+f67r1:-f8v` | adds pages or whole bifolia to a group and removes them, each group with its own edits. Search covers the whole manuscript by page, bifolium, section or Golf group. Undo goes back through this session's changes, and Reset group restores the group. The heatmap and every layer follow the edited group, its total included, and colours stay as they were |
| Wheel, drag, Fit, + − | none | zoom and pan, shared by the panels and kept across groups. Drag works at any zoom and past the edge of the frame, with at least 15% of the view left on it, so pages can be moved off the left margin. Fit returns |

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

## Why the default anchor

An opening word is usually at the left margin, but not always. The first paragraph of f84v is two short lines at the top right, above
a drawing, so on its opening word that page sits about 500 px left of the rest of Bio, though its boxes are correct. Taking x from the text's left edge
instead brings the spread of left margins within Bio from about 115 px to 18, and within Stars B from 34 to 12, keeps the same pages, and moves each
page by one translation. The leftmost box is used rather than the median line start, because on f36v and f67r2 most lines wrap a drawing and
the median falls some 300 px inside the margin. One stray box can still shift a page: 8 of 206 pages have a leftmost box over 60 px from the median line start.

## Reading it carefully

- Pages or paragraphs meet at the anchor by construction. That convergence is not evidence of a shared template.
- Marks are not normalised by group size, so a larger group looks denser. The heatmap is the comparable layer.
- Only horizontal lines are drawn. Rings and rays are in Compare's Wheels view, so the Zodiac group shows little here.
- Pages without a usable anchor are named under the figure. In this data, 225 of 227 pages align on their opening word, and 710
  of 736 paragraphs align under All paragraph starts.

## Origin

The method comes from the Section layout view of the 2026 bifolium drift study. This page runs it on the toolkit's corrected
data. It leaves out that view's gap areas and gap matching, JSON export and wheel panels.
