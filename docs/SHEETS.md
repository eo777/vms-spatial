# Odd-shaped sheets

Eleven of the 52 bifolia are not two plain leaves of single pages. Nine have foldout leaves, and two have lost a leaf.
`vmsspatial/resources/sheets.json` records their structure and the lines placed on their photographs. `vmsspatial.sheets` reads it.

- **`vmsspatial.leaves`** takes each foldout page's fold from those lines (`fold_method` 'sheet').
- **The Light table** draws the foldout leaves at their measured widths (`sheets` in `viewer/data/compare/pages.json.gz`).
- **Checks:** `sheets.check()` tests the resource against the physical map, and `tests/test_sheets.py` and `viewer/test/sheet_math.test.js`
  test the rest.

The audit below was made on 2026-11-04. Its sources are the Beinecke Library's scans (MS 408) and R. Zandbergen's quire descriptions on
voynich.nu (q02, q09, q10, q11, q12, q14, q15, q17, q19).

## What is recorded

For each foldout leaf, the resource records three things:

- **Its panels.** They are counted out from the binding fold, and each page lists the panels it lies on. f101r and f101v each lie on both
  panels of their leaf.
- **Its photographs.** Each records the vertical lines on the full-size scan, in px at mid-height:
  - `fold`, the binding;
  - `k|k+1`, the crease between two panels;
  - `k fold`, a further fold inside panel k;
  - `edge`, the outer edge.
- **Which face each panel's width is read on** (`use`, with the reason in `use_why`).

**How the lines are placed.** A fold or crease is a line that runs the full height of the scan (`leaves.edge_scores` over 10 to 90% of the
height).
- **Between two pages on one photograph:** it is the strongest line in the gap between their text.
- **Beside a panel photographed alone:** it is chosen among the lines there so that the panel's width, and the place of any further fold,
  agree with the other face.

Each line was then checked by eye. An outer edge is where the parchment meets the black ground at mid-height. Scan px become mm at the
scans' common scale, 15.84 px/mm, except where `vmsspatial.leaves` gives a scan its own (below).

**Which photograph is trusted.** A panel's width is read where it lies flat with both of its lines clear. A photograph can under-read a panel
that curls or folds over, and over-read one whose edge runs into the stack of leaves. The other face's reading is kept as a check.

**A panel read on each face** (`own`). Each page's words are placed from that page's own fold, the edge where the leaf meets the binding.
Where the binding hides a different strip of the panel by it on each face, that panel is read on each face's own photograph. Only f101's
first panel needs it:
- On 1006251 its crease lies 151 mm from the verso's fold, in a clear gap in f101v's text, and f101v's text runs 278 mm out from its fold.
- On 1006249 the crease lies 138 mm from the recto's fold.
- Drawn at the recto's widths, f101v's text would reach the outer edge and the crease would cut four of its words.

## The sheets

| Sheet | Shape | Panel widths, from the fold (mm) | Checks and notes |
|---|---|---|---|
| B:12-13 | f13 alone | — | Folio 12 is missing; a stub remains (q02). |
| L:73-74 | f73 alone | — | Folio 74 is lost, most likely cut out; a cut mark shows on f75 (q12). |
| I:67-68 | f67: two panels; f68: three, the third nearly square with a further fold | f67 147.7, 149.0 · f68 147.5, 129.8, 213.6, its fold 126 mm into panel 3 | The gathering mark is on f67r1: Zandbergen reads the bifolium as bound the wrong way round. On f68, the recto spread under-reads panel 1 (in the gutter) and panel 3 (skewed), so the verso is used for those two. |
| J:69-70 | f70: two panels, the second nearly square with a further fold | 146.2, 215.2, its fold 129 mm into panel 2 | The two faces agree within 4 mm. |
| K:71-72 | f72: three panels, the third with a further fold; f71 ordinary | 154.3, 147.2, 217.2, its fold 128 mm into panel 3 | Scan 1006203 (f71v and f72r) was photographed at another distance: at the common scale its leaves measured 168 to 175 mm. It now has its own scale, 12.23 px/mm, and the widths are read on the versos, at the common scale. f71v's fold is placed, because the scan's own was not measured. |
| N:85-86 | three panels across, two down; the Rosettes inside | — | See docs/LIGHTTABLE.md. The outside's upper row is upside down. fRos is leaf 85 verso, on the inner face. |
| O:87-90 | f90: two panels | 150.0, 157.8 | The second panel curls on the recto spread, so the verso is used. |
| O:88-89 | f89: two panels, the second wide with a fold through the middle | 151.0, 237.6, its fold 137 mm into panel 2 | The two faces agree within 5 mm. |
| Q:94-95 | f95: two panels | 151.8, 160.6 | The second panel curls on the recto spread, so the verso is used. |
| S:99-102 | f102: two panels, the second wide with a further fold | 148.0, 176.0, its fold 126 mm into panel 2 | Parchment is torn off the bottom of three pages. |
| S:100-101 | f101: one page each side, across two panels | recto 138.1, 139.6 (278 mm across); verso 151.3, 139.6 | The verso is photographed in two parts. The binding hides about 13 mm more of the first panel on the recto, so that panel is read on each face (below). |

Eight outer versos carry their leaf's folio number top right, as a recto would: f68v2, f70v2, f72v2, f89v2, f90v2, f95v2, f102v2, and
the outer part of f101v (Zandbergen). Several are photographed lying in the book like rectos. On those leaves, the outer panels fold over
the recto side when the leaf is closed, so the outer verso is the first page seen.

## What the audit changed

- **The Rosettes' face.** fRos was on leaf 86, in the outer face. It is now leaf 85 verso, on the inner face, in both physical maps:
  `data/manuscript/physical_map.csv` and the Golf study's copy.
- **One scan's scale.** f71v, f72r1, f72r2 and f72r3 were drawn about 22% too small, because their scan was taken at another distance. A scan
  whose own leaves all measure more than 10% off now takes its own scale.
- **Top edges.** Eight pages had their top edge on a drawing or a torn bottom: f101r, f70r2, f68r3, f68v3, f72v3, f95r2, f90r2 and f102r2.
  - Some now take the strongest top and bottom pair a leaf's height apart.
  - The others take the top of the panel beside them (`top_method` 'panel').
  - f72r3's top was wrong for the same reason and is fixed by its scan's scale.
- **Folds.** 21 foldout pages take their fold from the placed lines: every panel away from the binding, and f71v. Their old folds were
  estimated from the median inner margin and were off by up to 24 mm, on f72r2.
- **Widths.** The Light table draws every foldout leaf at its measured widths, with creases and further folds dashed.
- **f101v (2026-11-05).** Its display image shows only its first panel, and the words clipped off it had broken the display transform. Fitted
  on the words of that panel alone, f101v registers on scan 1006251 (991 SIFT inliers, 0.7 px), and its fold, top edge and scale are measured.
  The scan's fold lies 0.3 mm from the placed line.
- **The Rosettes (2026-11-05).** The drawing is placed whole, by its fold's mean place and the horizontal crease. Anchored row by row, the
  lean of the fold on the photograph had broken the middle row of rosettes at the horizontal crease.

## Checks

- Where a page's own binding fold is measured on its scan, the placed binding line agrees with it within 0 to 3.3 mm, on 17 pages.
- On every foldout page, every word lies on its own panels, within 3 mm. That is 6,699 words, with the Rosettes sheet.
- No word of f101v crosses its crease.
- Each placed fold was drawn on its scan and seen to sit on the crease.

## Open

- **f101's faces behind each other.** Each face is placed from its own fold, so where the binding hides 13 mm more of the recto, the face
  underneath on the Light table sits about 13 mm off its true place behind the face up.
- **Faces that disagree by more than 5 mm.** These are left as read: f68 panels 1 and 3, f72 panel 3, f90 panels 1 and 2, f95 panel 2,
  f102 panel 1 and f101 panels 1 and 2. The differences are those of the photographs: curled flaps, gutters and stacks.
- **The Rosettes.**
  - Their creases are placed by eye on the quarter-size scan, to about 5 mm. The fold leans on the photograph, about 9 mm between the rows,
    so a word close to it can sit up to about 4 mm from where its own half's fold would put it.
  - The folds of the outside's upside-down panels are the margin estimate, reflected about the text.
- **Not modelled.** The strip of leaf hidden in the binding, and the parchment strips sewn into quires 9 and 17.
