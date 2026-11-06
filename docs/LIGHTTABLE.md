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

## Margins and text angle

Both are off unless chosen (Margins, Text angle), and both are drawn for every page shown, in its colour, on either face. Behind, they are
dashed and mirrored with the page's words. They are computed in `sheet_math.js` (`margins`, `tilt`) from the same page data as the words.

- **Margins** trace each page's text edges.
  - On the left, a dot is the left end of a full paragraph row that is not its paragraph's first. These are the Page stream's margin points
    (`stream_math.marginRows`).
  - On the right, a dot is the right end of a full paragraph row that is not its paragraph's last, since a paragraph's last line stops short.
  - A row is full when it is a horizontal paragraph line of at least three boxes holding every token of the line.
  - A line joins only consecutive rows, so a gap stays a gap.
  - The trace follows the writing: where a line goes round a drawing or stops short inside a paragraph, so does the trace (three rows of f1r end
    60 to 86 mm from the fold, where its other rows end at about 128 mm).
  - Behind, a page's left edge lies on the right.
- **Text angle** is each page's median line angle as its words are drawn, positive where the lines fall to the right (`drift` in the page
  data, docs/STREAM.md). It follows the coordinates:
  - in Flat, the angle after flattening (`drift.flat.angle`), which takes the page's tilt out: 0.09° at the median of the 202 pages that have one,
    0.63° at most;
  - in Recorded, the angle as written (`drift.recorded.angle`): 1.14° at the median.
  - It is drawn as a solid line at that angle, with the level dotted through the same point and as long, and a dot at that point.
    - **Place.** The line goes through the mean centre of the boxes of the lines it is the median of. Under View, At: the middle of the page
      puts it at the middle of the page's leaf instead, the same place on every page.
    - **Length.** The line is as wide as those lines run. Under View, Length: equal makes it 100 mm on every page (`EQUAL_MM`).
    - **Exaggerate.** Under View, each line can be drawn 2 to 100 times as steep as its angle (`ANGLE_SCALES`), never past 85°
      (`MAX_DRAWN`), about the same point and at the same length. Most pages lie within a degree or two of one another as written (0.22° to
      2.53° from the 10th to the 90th percentile), and within a few tenths after flattening (0.02° to 0.24°), too little to compare by eye.
      The values stay true, and a note in the table's top right corner says how much the lines are drawn up ("Angles drawn ×20").
    - These choices can be made independently of one another (`tiltLine` in `sheet_math.js`).
  - Its value, in degrees after a dot of its page's colour, stands beside an end of its own line: past the right end, else before the left,
    a line higher or lower where those are taken. The values are laid out with the sheets' tags (below), so none covers another value or a
    tag, and none is cut off at a leaf's edge. Values, under View, turns them off. Behind, the line is mirrored and so falls the other way,
    and its value is still the angle as written.
  - Hovering a word gives its page's angle both as written and after flattening, and the number of lines.

## Labels

Under View, Labels sets where the names go.

- **Sheet names** writes each piece's name and the face it shows on the sheet (the default), above it, or not at all.
  - **On the sheet:** at the top right corner of the face up, a row lower for each piece, so stacked pieces keep theirs apart.
  - **Above:** each face shown has a tag in the space over its sheet ("A:2-7 (2) · outer"; a leaf's says recto or verso), with a square of its
    colour. Each tag goes where it covers the fewest pages and no other tag. It tries over the sheet first, side by side along its width and
    then in rows upwards, and under the sheet where there is no room over it. So the tags of sheets lying on one another sit together over
    them. The tags are laid out in the pieces' own order, which selecting one does not change, so a tag stays put under the pointer.
  - A click on a tag selects its sheet, and dragging it moves the sheet. The selection's toolbar keeps clear of the selection's tags. The table
    opens, and Fit fits, with room for a row of tags over the top sheets.
- **Page names** writes each page's name at its leaf's corner (the default, with each name behind at the bottom corner), above its leaf, or
  not at all. Above, each page of the face up has a tag over its own leaf ("f7v"), with a square of its colour, laid out with the sheets' tags
  and before them, so the pages' names lie nearest their pages. With both kinds above and little room between the rows of a layout, a sheet's
  tag can go further up, or past its sheet's right edge into the space beside it, before it covers a page.
- **Copy numbers** off leaves the (2) of a second copy out of the names on the table. The Pieces list and the selection's toolbar keep it.
- **What they are measured against.** Both are measured in the photograph's frame, not against the edge of the parchment.
- **Lines** (View, Show) draws each horizontal paragraph line as plotted, through its words' baseline anchors (`baselines` in `sheet_math.js`;
  a word anchored at its box's centre is left out), in the page's colour, in the coordinates the words are drawn in, and at their true slope:
  Exaggerate does not touch them. The lines the text angle is the median of are solid, the others dotted. Behind, all are dotted.
- **Coverage.** 206 of the 227 pages have a left margin and 205 a right margin. 202 have a text angle; the rest have no horizontal paragraph
  lines that qualify (the astronomical foldouts, f57v, f65r, f73r and f73v among them, and the Rosettes). The notes name any page shown without
  one.

## Leaves and copies

- **Divide** cuts a sheet at its fold into its two leaves (folios): leaf A holds Ar and Av, leaf B holds Bv and Br. Each is left where it lay,
  in the sheet's colour, and moves, turns and shows its pages on its own. **Join** makes the sheet whole again where the leaf you join from lies,
  with that leaf's face up.
- **A leaf turns over where it lies.** Its bound edge goes to the other side, as when a loose leaf is turned on the table. A whole sheet turns
  about its fold, which stays put.
- **Adding a leaf.** In Add sheet's list each bifolium shows its two leaves by folio (for A:1-8, f1 and f8). Choosing one puts that leaf on the
  table on its own.
- **Copies.** The same bifolium or leaf can go on the table more than once. Each copy is numbered, named so in its row (A:1-8 (2)), and takes
  the next free colour. A leaf added while its other leaf lies alone on the table joins that copy, and takes its colour.

## The page

The page does not scroll. A menu bar runs along the top, under the site's links, and the table fills the rest of the window. The table has no
edge and no scroll bars: it pans and zooms, as a whiteboard does.

- **The menu bar.**
  - **Add sheet** opens the list of bifolia, with a search box.
  - **Edit** holds Select all, Turn over, Divide or join, Remove, Stack at the fold, Spread out, Snap to guides and Clear the table.
  - **View** holds which pages are drawn, what is drawn over them, the opacities, the colouring and the coordinates.
  - **Pieces** lists the pieces on the table.
  - On the right are the zoom (−, the menu, +, Fit) and **?**, the help. The help holds the status line, the notes on what is drawn and the
    page's own guide.
- **Selecting.** A click selects a piece, and Shift-click (or Ctrl-click) adds another or takes it away. Drawing a box on the empty table
  selects every piece it touches. A selected piece gets an outline on the edges of its face-up leaves. The selection comes to the top of the
  stack.
- **The selection's toolbar** floats over the selected pieces, or under them where there is no room. It holds:
  - the piece's name and the face that is up, or how many pieces are selected;
  - the colour, the opacity, Turn over, Both faces, and Divide or Join;
  - for one piece, Pages, which shows its pages' boxes;
  - Duplicate and Remove.
- **Both faces** puts a piece's other face beside it, to the right, 20 mm past it (`pair` in `sheet_math.js`). The two are linked: they move,
  turn, change colour and are removed together. Nothing is drawn behind either face, neither its words nor its margins nor its angle, so each
  physical face of the sheet can be read on its own, side by side.
- **Duplicate** (Ctrl D) puts a copy of each selected piece, as it is (face, pages, colour, opacity, both faces), to the right of the
  selection, and selects the copies. Two leaves of one copy stay one copy.

## Controls

| Control | Address | What it does |
|---|---|---|
| Add sheet | `sheets` | lists every bifolium with its section and its two leaves' folios. The search box matches a name (A:1-8), a folio (f68, or 68) or a section, every word typed. Enter adds the first match as a sheet, and the arrow keys move through the list. A bifolium's name adds the whole sheet beside the last piece, or on a new row, and a folio adds that leaf alone. Either comes into view, selected. Up to 24 pieces; the first six copies take the six categorical colours, in the order added, and any later one is drawn in ink |
| Click a piece; Shift-click; a box drawn on the empty table; Ctrl A | none | selects, as above. A click on one piece of several selected selects it alone; a click on the empty table, or Escape, lets go |
| Drag a selected piece | `sheets` | moves every selected piece together, exactly where they are put unless Snap to guides is on. A press that moves no more than 3 screen pixels is a click |
| Arrow keys | `sheets` | move the selection 0.5 mm a step, 5 mm with Shift, 0.1 mm with Alt. F turns it over, D divides or joins, Delete removes it |
| Drag with the right or middle button, or with Space held | none | pans the table |
| The wheel; −, the zoom menu, +; Fit | `zoom` = any value from 0.3 to 8 (1.5 is the default) | screen pixels a millimetre. The wheel zooms about the pointer, keeping the millimetre under it in place; −, + and the menu (0.75, 1, 1.5, 2, 3, 4) about the middle of the table; Fit (Shift 1) fits the selection, or every piece, to the table. The keys − and + zoom too |
| The selection's colour square | `sheets` | chooses its colour: one of the six sheet colours or ink, or any colour with Custom (the browser's colour picker). Both leaves of a divided sheet take it. A chosen colour stays as picked in the light and dark themes; the six sheet colours are stepped for each |
| The selection's Opacity | `sheets` | the opacity of the selected pieces, 10 to 100% |
| Both faces | `sheets` (`,t` after a piece) | shows the piece's other face to the right, linked, with nothing behind either face, as above |
| Duplicate (Ctrl D), on the toolbar or under Edit | `sheets` | a copy of each selected piece, as it is, to the right; the copies are selected |
| Turn over (F) | `sheets` | turns a sheet over about its fold, or a leaf over where it lies |
| Divide or Join (D) | `sheets` | as above; the leaves, or the whole sheet, stay selected |
| Pages, on the toolbar or in a row; Outer, Inner in a row | `sheets` | shows or hides a page's words, or every page of that sheet's outer face (Bv, Ar) or inner face (Av, Br) at once. Foldout panels of one position switch together |
| Edit: Stack at the fold | `sheets` | puts each piece's fold edge and top edge on the first one's, as nested in a quire: the selection's, when two or more are selected, else every piece's |
| Edit: Spread out | `sheets` | lays the pieces out in rows across the table's width: the selection from where it starts, or every piece from the view's corner |
| Edit: Snap to guides | `snap=1` (off is the default) | while a piece is dragged, a fold or edge within reach of a guide jumps onto it, across and down separately. The arrow keys still move it exactly |
| Edit: Clear the table | `sheets` | removes every piece |
| View: Outer face, Inner face | `sheets` | shows or hides the text of that face on every piece on the table; part checked when some pieces show it |
| View: Visible face, Face underneath | `faceup=0`, `under=0` (both drawn is the default) | draws or leaves out the text of the face up on every piece, as read, and of the face underneath, seen through, whichever physical face each is |
| View: Words | `words=1` | writes each word's EVA spelling in its box, no wider than the box, once it is at least 7 screen pixels tall: from about 2 px/mm for ordinary text. Words on the face underneath are written the right way round, for reading, at their mirrored places |
| View: Word direction, shown with Words when a ring or turned line is on the table | `wdir=level` (ring is the default) | how the words of rings, radial and rotated lines and steep labels are written, from each line's orientation record (`js/word_labels.js`, as on the Atlas and Compare pages). Bottom to centre writes each along the writing, its bottom towards the wheel's centre, or along the line's chord. Level stands them upright, where they can run past their boxes. Either way one size serves the page, from each word's length along its own direction rather than its box's width, so the words at 3 and 9 o'clock are as big as those at 12. Behind, mirrored, they turn the other way, so they still read the right way round. Level text keeps its box fit |
| View: Margins | `margins=1` (off is the default) | traces each page's text edges, as above |
| View: Text angle | `angle=1` (off is the default) | draws each page's median line angle as its words are drawn, against the level, as above |
| View: Text angle, At | `angleat=page` (the text's centroid is the default) | where each angle line is drawn: through the centroid of the page's paragraph text, or the middle of its page |
| View: Text angle, Length | `anglelen=equal` (as wide as the text is the default) | how long each angle line is: as wide as the text, or 100 mm on every page |
| View: Text angle, Exaggerate | `anglex` = 2, 5, 10, 20, 50 or 100 (1, the true angle, is the default) | draws each angle line that many times as steep, up to 85°; the values stay true, and the table's corner says how much the lines are drawn up |
| View: Sheet names | `sheetlabel` = above or off (on the sheet is the default) | where each piece's name and the face it shows are written, as above |
| View: Page names | `pagelabels` = above or off (at the leaf's corner is the default) | where each page's name is written, as above. An older address's `pagelabels=0` or `labels=0` turns them off (`labels=0` the sheets' too) |
| View: Copy numbers | `copies=0` (on is the default) | names a second copy A:2-7 (2) on the table, or A:2-7 |
| View: Lines | `lines=1` (off is the default) | draws each horizontal paragraph line through its words' baseline points, as above |
| View: Text angle, Values | `anglev=0` (on is the default) | writes each line's true angle beside it, or leaves it off |
| View: Guides | `guides=0` (on is the default) | while a piece is dragged (gone when it is let go), and for a moment after an arrow key, a line shows each fold or edge of another piece that one of its own comes within 1 mm of (6 screen pixels at small zooms), and its top edge the other's top or bottom: fold on fold, fold on an outer edge, side by side, level, or one above another. The label gives how far off it is; the line turns solid and reads aligned within 0.05 mm |
| View: Dim word boxes | `dim=1` | steps every word box back to 30% of its strength, so the margins and angles stand out |
| View: Opacity sliders | `op=boxes,under,margins,angles,lines,paper` in percent (100 each is the default) | the strength of the word boxes on the face up, of those on the face underneath, of the margins, of the angles and their values, of the lines, and of the leaves' tint, each on its own, on every piece at once. An older address's four values set the margins and angles together |
| View: Colour | `colour=face` (sheet is the default) | One per sheet gives each copy its own colour. Outer and inner faces colours every page by the physical face of its sheet: the outer face's Bv and Ar the first colour, the inner face's Av and Br the second, wherever the piece lies and whichever side is up. Where pieces overlap, each one's filled words show which side of its sheet is up, and its outlined words the other side. The leaves' outlines are then in ink, and the square by each page's label takes its face's colour too, so colour means the face alone; the labels name the pieces. The two squares beside the menu choose the faces' colours, as a piece's square does (`fc=outer,inner`, each a colour as in the address below; 1,2 is the default) |
| View: Coordinates | `coords` = recorded (flat is the default) | as above |
| Pieces | `sheets` | a row a piece: its colour, its name (which selects it and brings it into view), the face up (which turns it over), its pages, where it lies against the first piece, Divide or Join, and Remove |

A piece in the address is `node[/A|/B][~copy]@x,y,face,pages,colour[,opacity][,t]`, pieces joined by `|`: `/A` or `/B` is one leaf, `~2` the second
copy; x and y are the piece's fold edge, less 160, and its top edge, in table millimetres, anywhere within 5,000 mm of the table's corner; face is
`o` or `i`; pages is a hexadecimal mask over Bv 1, Ar 2, Av 4, Br 8; colour is 1 to 6, one of the six sheet colours, 0 for ink, or six hexadecimal
digits for a colour picked (`c0ffee`); opacity, when the piece is not opaque, is 10 to 99 percent; `,t` shows both faces. A copy is on the table whole or as its leaves,
never both. With no `sheets`, the table opens on the manuscript's first two bifolia side by side. Where the table is looked at, the camera, is
not kept.

Each row gives its piece's fold edge and top edge in millimetres from the first piece's. Hovering a word names its page, line and spelling, says
whether it is on the face up or the face underneath, and gives its page's text angle.

## Reading it carefully

- Positions are display choices. Nothing on this page is scored, and no measure is read from it.
- The face underneath is the same page mirrored, not a photograph of show-through. Whether ink actually shows through is a question for the
  scans.
- Leaf edges come from the scans, and each is good to about 1 to 2 mm at the fold and 2 to 3 mm at the top (docs/STREAM.md). Two sheets set
  fold to fold can still differ by that much where the real leaves did.
