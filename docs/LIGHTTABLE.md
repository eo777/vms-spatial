# Light table

`viewer/lighttable.html` lays bifolia on a table as open sheets, to move by hand. The model, the alignment guides and the address are in
`viewer/js/sheet_math.js`, tested in `viewer/test/sheet_math.test.js`.

## The sheet

A sheet is one bifolium opened flat. Each leaf is the catalogue's 160 × 225 mm, and the fold, dashed, runs between the two leaves. The
outer face is Bv | Ar and the inner face Av | Br, as in the physical faces of the Page stream and Word search. Turning the sheet over
about its fold puts Av behind Ar and Br behind Bv.

- **The face up** is drawn as read, its words filled.
- **The face underneath** is mirrored about the fold, its words in outline. Each of its pages then lies behind its partner on the same leaf,
  as if the sheet were held up to the light.
- **Placement.** Each page is in millimetres from its fold and its leaf's top edge, at its own scale, from the Page stream's parchment
  scale (docs/STREAM.md, `vmsspatial.leaves`). With either face up, every word of every page with a measured fold and top edge lies on its own leaf,
  within 2 mm, which the tests check on the real data. The strip of a leaf hidden in the binding is not measured, so a gap across a fold can
  be a little short.
- **Coordinates.** Flat, the default, takes each page's shared curve and tilt out of the vertical positions (docs/DEWARPING.md). Recorded keeps
  them as drawn.
- **Foldouts.** Every foldout leaf is drawn at its measured widths, its creases and further folds dashed, each page on its own panels. The
  widths come from the photographs of the leaf, `sheets` in the page data, built from `vmsspatial/resources/sheets.json` (docs/SHEETS.md, the
  audit of the odd-shaped sheets). f101r and f101v each run across both panels of their leaf. On f101 the binding hides about 13 mm more of the
  panel by the binding on the recto than on the verso, so that panel is drawn at each face's own width: 138 mm on f101r, 151 mm on f101v. The
  recto's crease then shows dotted behind the verso, 13 mm nearer the fold. The verso of each panel lies behind its recto. The Rosettes sheet is
  drawn by its own grid, below.

## The Rosettes sheet

N:85-86 is drawn folded as it is: three panels across and two down. The layout comes from the Beinecke photographs of the sheet (scans 1006228 to
1006231, in the image cache) and R. Zandbergen's description of quire 14 (voynich.nu/q14). Its grid is in `vmsspatial/resources/sheets.json` (docs/SHEETS.md).

- **Bound at the lower half.** The sheet is sewn in at the vertical crease of its lower half, with one panel (f85) on one side and two (f86) on
  the other. The upper half is a flap that folds down over the lower half.
- **Inside: the Rosettes.** fRos fills all six panels, f85v | f86r: one column of f85v, then two columns of f86r. The drawing is placed whole,
  as photographed, at one scale, by its fold and its horizontal crease, so the rosettes run on unbroken across the creases. Each word goes with
  the leaf it lands on, so on the table it is two pieces: fRos (f85v) on leaf A and fRos (f86r) on leaf B. The Rosettes' fold, outer crease and
  horizontal crease are placed by eye on the toolkit's quarter-size copy of scan 1006231, to about 5 mm.
  - On the photograph the fold leans: it lies about 9 mm further out in the upper half than in the lower. The drawing takes the fold's mean
    place, so a word close to the fold can sit up to about 4 mm from where that half's own fold would put it.
  - Anchoring each row at its own fold, as before 2026-11-05, broke the middle row of rosettes at the horizontal crease.
  - The outer crease is a check: it lands within 3 mm of the panel edge.
- **Outside: two rows, one of them upside down.** With the outer face up, the lower row is f86v5 | f86v3 | f85r1 and reads the same way up as
  the Rosettes. The upper row is f86v6 | f86v4 | f85r2, and is written upside down. It reads upright only when the upper half is folded down over
  the lower, which is how scan 1006229 shows f85r2, f86v4 and f86v6 side by side across the binding.
  - Scan 1006230 shows f86v5 and f86v3 side by side, and 1006228 shows f85r1 alone.
  - f85r1 and f86v3 meet across the binding, as do f85r2 and f86v4: Zandbergen gives each pair as opposite pages.
- **What lies behind what.** With the outer face up, the Rosettes' f85v column lies behind f85r1 and f85r2, and their f86r columns lie behind
  the four f86v panels, row for row. The middle row of rosettes straddles the horizontal crease.
- **Placement.** Each panel is a catalogue leaf, anchored at its side toward the fold and at the horizontal crease, which is each outside
  panel's own top edge as photographed. On an upside-down panel the side toward the fold is the far side of the page as read. Its fold is
  estimated from the median inner margin, by `vmsspatial.leaves`, on the near side, so here that estimate is reflected about the page's text. Only
  f85r1's fold is measured. Every word of the seven pages lies on its own panel, which the tests check.
- **Words.** The words of an upside-down panel are drawn the way they are written, turned half way round. Word direction Level stands them
  upright, as it does the words of rings.
- **Elsewhere in the toolkit.** The physical record (`data/manuscript/physical_map.csv`) has fRos on leaf 85, verso, so on the inner face, in
  the A verso slot (corrected 2026-11-04; it had been leaf 86, on the outer face). The other pages show it as one page in that slot. Only this page
  splits it across the fold and folds the sheet.
- **Not drawn.** A page with no parchment record (f116v) cannot be placed, and the note says so.

## Leaves and copies

- **Divide** cuts a sheet at its fold into its two leaves (folios): leaf A holds Ar and Av, leaf B holds Bv and Br. Each is left where it lay,
  in the sheet's colour, and moves, turns and shows its pages on its own. **Join** makes the sheet whole again where the leaf you join from lies,
  with that leaf's face up.
- **A leaf turns over where it lies.** Its bound edge goes to the other side, as when a loose leaf is turned on the table. A whole sheet turns
  about its fold, which stays put.
- **Adding a leaf.** The arrow beside Add sheet opens a menu of the chosen bifolium's two leaves, named by folio (for A:1-8, f1 and f8). Choosing
  one puts that leaf on the table on its own.
- **Copies.** The same bifolium or leaf can go on the table more than once. Each copy is numbered, named so in its row (A:1-8 (2)), and takes
  the next free colour. A leaf added while its other leaf lies alone on the table joins that copy, and takes its colour.

## Controls

| Control | Address | What it does |
|---|---|---|
| Bifolium, Add sheet, and the arrow beside it | `sheets` | Add sheet adds the bifolium beside the last piece; the arrow's menu adds one of its leaves instead. Up to 24 pieces; the first six copies take the six categorical colours, in the order added, and any later one is drawn in ink |
| Drag a piece | `sheets` | moves it, exactly where it is put unless Snap to guides is on |
| Guides | `guides=0` (on is the default) | while a piece moves, and for a moment after, a line shows each fold or edge of another piece that one of its own comes within 1 mm of (6 screen pixels at small zooms), and its top edge the other's top or bottom: fold on fold, fold on an outer edge, side by side, level, or one above another. The label gives how far off it is; the line turns solid and reads aligned within 0.05 mm |
| Snap to guides, under Settings | `snap=1` (off is the default) | while a piece is dragged, a fold or edge within reach of one of those lines jumps onto it, across and down separately. The arrow keys still move it exactly |
| Click a piece; click the empty table | none | a click chooses a piece, brings it to the top and marks its row; a click on the empty table lets go of it |
| Arrow keys on a selected piece | `sheets` | 0.5 mm a step, 5 mm with Shift, 0.1 mm with Alt. F turns it over, D divides or joins, Delete removes it |
| Outer / Inner face up; Recto / Verso up | `sheets` | turns the sheet over about its fold, or the leaf over where it lies |
| Divide / Join | `sheets` | as above |
| A page's box in a piece's row | `sheets` | shows or hides that page's words. Foldout panels of one position switch together |
| Outer, Inner in a sheet's row | `sheets` | shows or hides every page of that sheet's outer face (Bv, Ar) or inner face (Av, Br) at once |
| Outer face, Inner face | `sheets` | shows or hides the text of that face on every piece on the table; part checked when some pieces show it |
| The colour square in a piece's row | `sheets` | chooses its colour: one of the six sheet colours or ink, or any colour with Custom (the browser's colour picker). Both leaves of a divided sheet take it. A chosen colour stays as picked in the light and dark themes; the six sheet colours are stepped for each |
| Words | `words=1` | writes each word's EVA spelling in its box, no wider than the box, once it is at least 7 screen pixels tall: from about 2 px/mm for ordinary text. Words on the face underneath are written the right way round, for reading, at their mirrored places |
| Word direction, shown with Words when a ring or turned line is on the table | `wdir=level` (ring is the default) | how the words of rings, radial and rotated lines and steep labels are written, from each line's orientation record (`js/word_labels.js`, as on the Atlas and Compare pages). Bottom to centre writes each along the writing, its bottom towards the wheel's centre, or along the line's chord. Level stands them upright, where they can run past their boxes. Either way one size serves the page, from each word's length along its own direction rather than its box's width, so the words at 3 and 9 o'clock are as big as those at 12. Behind, mirrored, they turn the other way, so they still read the right way round. Level text keeps its box fit |
| Colour | `colour=face` (sheet is the default) | One per sheet gives each copy its own colour. Outer and inner faces colours every page by the physical face of its sheet: the outer face's Bv and Ar the first colour, the inner face's Av and Br the second, wherever the piece lies and whichever side is up. Where pieces overlap, each one's filled words show which side of its sheet is up, and its outlined words the other side. The leaves' outlines are then in ink, and the square by each page's label takes its face's colour too, so colour means the face alone; the labels name the pieces. The two squares beside the menu choose the faces' colours, as a piece's square does (`fc=outer,inner`, each a colour as in the address below; 1,2 is the default) |
| Stack at the fold | `sheets` | puts every piece's fold edge and top edge on the first piece's, as nested in a quire |
| Spread out | `sheets` | lays the pieces out in rows across the table |
| The wheel; Zoom | `zoom` = any value from 0.3 to 8 (1.5 is the default) | screen pixels a millimetre. The wheel zooms about the pointer, keeping the millimetre under it in place; the menu has 0.75, 1, 1.5, 2, 3 and 4 |
| Drag the empty table; middle-button drag | none | pans the table |
| Coordinates, under Settings | `coords` = recorded (flat is the default) | as above |
| Clear the table, under Settings | `sheets` | removes every piece |

A piece in the address is `node[/A|/B][~copy]@x,y,face,pages,colour`, pieces joined by `|`: `/A` or `/B` is one leaf, `~2` the second copy; x
and y are the piece's fold edge, less 160, and its top edge, in table millimetres; face is `o` or `i`; pages is a hexadecimal mask over Bv 1, Ar 2,
Av 4, Br 8; colour is 1 to 6, one of the six sheet colours, 0 for ink, or six hexadecimal digits for a colour picked (`c0ffee`). A copy is on the
table whole or as its leaves, never both. With no `sheets`, the table opens on the
manuscript's first two bifolia side by side.

Each row gives its piece's fold edge and top edge in millimetres from the first piece's. Hovering a word names its page, line and spelling, and
says whether it is on the face up or the face underneath.

## Reading it carefully

- Positions are display choices. Nothing on this page is scored, and no measure is read from it.
- The face underneath is the same page mirrored, not a photograph of show-through. Whether ink actually shows through is a question for the
  scans.
- Leaf edges come from the scans, and each is good to about 1 to 2 mm at the fold and 2 to 3 mm at the top (docs/STREAM.md). Two sheets set
  fold to fold can still differ by that much where the real leaves did.
