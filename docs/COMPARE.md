# Comparing two pages on their word rectangles

`vmsspatial.compare` lays the text block of one page over the text block of another with a single translation and
reports how much occupied area they share and how alike the wording is where the rectangles coincide. It is the
comparison workspace of the October 2026 bifolium study, ported to the toolkit so that every score can be recomputed
from the shipped bundle; the browser port is `viewer/js/compare_math.js`, and `viewer/data/compare/` holds the data
the atlas's comparison page reads. The scores are descriptive. A translation-only overlay says how far two blocks
resemble each other in placement and wording; it does not test whether one was copied from the other (PITFALLS 25).

## Concepts

**Unit.** A located rectangle of the page with the token or tokens it stands for (a shared rectangle is one unit:
"o eeockhy" on f21r), its text, its lossless EVA atoms (`vmsspatial.units.atom_strings`: benches `ch`, `sh`, pedestalled
gallows, ligatures and extended atoms whole, every other character on its own), its line, and a baseline anchor.
Units are ordered left to right on horizontal lines and in stream order elsewhere.

**Anchor.** One point per unit on the writing line: the toolkit's baseline point (`baselines.word_baselines`,
method `'auto'` by default: the ink baseline where the page has clean ink records, the glyph-corrected box baseline
elsewhere; the October 2026 workspace used `'glyph'` everywhere, `prepare(..., baseline='glyph')`). A unit on a line
that is not horizontal (a label, a ring, a radial word) carries no baseline and uses a declared box-centre anchor
(`anchor_kind` says which).

**Block.** The page opening (the first five paragraph lines), the whole page, each canonical paragraph of the
transcription (`p1`, `p2`, ...: paragraph lines broken at the ZL paragraph starts) and each non-paragraph locus on
its own (`l<index>`). `compare.page_blocks` lists them; 740 paragraphs on the 227 pages.

**Body size.** H and W are the medians of the heights and widths of the page's paragraph-line rectangles (all its
rectangles when it has no paragraph line). They set the nearby window and the body-height scale.

## The selection model

```python
from vmsspatial import compare as C
data = C.load()                                  # sensitivity geometry, recorded state, 'auto' anchors; ~10 s
a = C.select(data, 'f20v', block='opening', cutoff=3, coordinates='flat', alignment='starts', scale='pixels')
```

| choice | values | meaning |
|---|---|---|
| block | `opening`, `page`, `p1`.., `l<i>` | which lines of the page |
| cutoff | 1..5, `'all'` | the top lines of the block that are scored (the rest stay as faint context) |
| coordinates | `flat` (default), `recorded` | flat: the stored page warp removed (`vmsspatial.warp`), the anchors moved by each box's own shift; recorded: the rectangles as drawn. x is the same in both |
| alignment | `starts` (default), `page` | starts: the block's first box's anchor becomes the origin; page: the page's opening anchor becomes the origin, a later paragraph keeps its position within the page, and only the opening box (when it is in the block) is excluded |
| scale | `pixels` (default), `body_height` | body height multiplies x and y by 30 / H of the page, independently per page; it removes writing size as well as magnification, so it is a sensitivity view |
| extent | `whole`, `top`, None | shortcuts: whole = `page` with `'all'`, top = `opening` |

A selection reports `available` (an anchor exists), `complete` (every requested line has located units), `located`,
`expected`, `nonhorizontal` (orientation kinds among the chosen units other than horizontal), and the frame and
warp tags of its coordinates. `measure` refuses two selections in different states. Composites (several pages to one
anchor) are several selections drawn in one frame: each is translated to its own anchor, nothing else.

The 2026 workspace's other coordinate variants (the study's own refit field, the shared-field glyph and ink anchors
on its 96 pages, "original flattened glyph refit") are study products and are not in the toolkit; its "current
stored correction" is `coordinates='flat'`, its "recorded" is `coordinates='recorded'`.

## The metrics

A = the chosen units of the first selection, B of the second, both translated.

**Occupied-area Dice** (`dice`). With |X| the exact area of the union of a set of rectangles (a sweep over the
distinct x edges, the y intervals merged in every strip),

    dice = 2 |A ∩ B| / (|A| + |B|)

where A ∩ B is the set of pairwise intersection rectangles. One rectangle and two adjoining rectangles covering the
same area score alike: a word boundary is not a mismatch. `same_row=True` restricts intersections to units with the
same line index and sums per line.

**Direct-overlap EVA similarity** (`local_segment_similarity`). Two units correspond when their intersection is at
least a fifth of the smaller rectangle's area (EDGE_SHARE = 0.2). For every unit u of A with correspondents N(u) in
B, and every unit v of B with correspondents N(v) in A,

    sim(u, N(u)) = 1 − edit(atoms(u), atoms(N(u)) joined in reading order) / max(lengths)
    local = Σ w · sim / Σ w,   w = |u ∩ N(u)| (the union area of the intersections)

over both directions. The correspondence is chosen by geometry alone; the text enters only through the edit
distance. One box may answer to several (a word written across the space of two).

**Nearby EVA similarity** (`nearby_similarity`). For every unit the best single-unit similarity among the units of
the other page within 0.5 W horizontally and 0.5 H vertically (gap to gap; W, H the means of the two pages' body
sizes), averaged over every unit of both pages that has such a neighbour. Targets may be reused.

**Per-line table** (`per_line`). Line i of A against line i of B with the blocks left where their anchors put them:
no realignment of the lines. The cumulative scores of a cutoff are not averages of these rows.

**Word-segment correspondences** (`details`). `direct`: each unit with its overlapping neighbours in either
direction; `connected`: the transitive connected groups of the overlap graph (they can chain across lines and are not
assumed to be one copied phrase); `nearby`: each unit's best nearby match. Every record has the texts, the edit
distance, the similarity, the lines and whether every unit is clean (one unflagged word-level token).

**Position-constrained EVA similarity** (`spatial_similarity`, the first-line scan's primary score). A Levenshtein
alignment of the two atom sequences in reading order in which a match or a substitution between two atoms costs 0 or 1
only when the x intervals of their parent boxes overlap by at least a fifth of the shorter interval, and 2 otherwise;
insertions and deletions cost 1; similarity = max(0, 1 − cost / longer sequence). A word may occupy the space of
several words without its boundaries counting as mismatches; rearrangements are not free.

**Horizontal-occupancy Dice** (`x_dice`): the Dice of the x intervals alone (identical in both warp states).

**Jensen-Shannon distance** (`js_distance`, `line_features`). The square root of the base-2 Jensen-Shannon divergence
between two histograms of adjacent Zattera unit pairs of the lines' transcripts: `js_word` weights every word
equally (within-word pairs, as `measures.Features`), `js_pooled` by pair count, `js_joined` joins the words into one
sequence so that pairs cross word boundaries (the segmentation kept), `js_boundaries` inserts a boundary unit. These
are composition distances: they do not see where the words stand.

**Bifolia** (`sheet_rows`, `compare_sheets`, `joint`). A flat bifolium's inner face is A verso beside B recto, its
outer face B verso beside A recto (`FACES`). Corresponding slots are compared page by page; the joint value is the
equal-page mean and the weaker-page minimum of each score, withheld unless every slot is complete. A foldout slot
with several panels resolves only by an explicit choice.

**Rankings** (`first_line_scan`, `rank_pairs`). Every page whose opening block's first line is a paragraph line,
horizontal and located enters the scan (205 pages); pairs where both lines are complete with at least two scored
boxes are eligible (20,100 of 20,910). Bifolium face rows need exactly one complete page in every required slot (inner
38 sheets, 703 pairs; outer 39, 741; all four slots 35, 595) and average their page pairs equally. The combined rank
minimises the worse of the Dice rank (`dice_current`, descending) and the JS rank (`js_joined`, ascending), then the
rank sum; ranks are competition ranks within the pool given, so a filtered pool re-ranks. Separate rankings by
`spatial`, `dice_current` or `js` are available.

**Layout** (`layout`, `paragraph_polygons`, `line_break_markers`). The whole page translated by its opening anchor
(or every paragraph by its own first-word anchor), with the intrusion breaks of `geometry.line_breaks` (ZL `<->` and
`<~>` between located words), the paragraph start and end spans and stepped envelopes of complete horizontal rows.

## What the scores do and do not mean

- They describe how two blocks resemble each other after one translation. Pages share layouts for many reasons
  (a drawing's shape, line length habits, a ruled margin); a high Dice is common between pages of one section.
- A rank in `rank_pairs` is a retrieval order, not a probability. Counts of controls at least as high as an observed
  pair include the pair itself and are made after the pair was chosen by eye.
- The first box is scored. Alignment puts the two first boxes on the same point, so their overlap is forced and lifts Dice
  a little, about 0.005 on a whole page and more on a short selection. It stays in because a page's opening word is often a
  hapax, which makes it the most telling word to compare directly. The page shows the two opening words beside the scores.
- `nearby_similarity` depends on the body sizes W and H; `body_height` scaling changes every score.
- A translation-only alignment cannot tell copying from a shared template or from writing habits; it has no direction
  (A on B equals B on A). Direction would need independent evidence (PITFALLS 25).
- The JS distances compare transcripts, not positions; `edit_all` and `js_*` ignore the rectangles entirely.

## The drift indicator and the inline line split

**Drift indicator** (`page_drift`, `drift_guide`). The workspace's pre-correction drift guide: for every horizontal
paragraph line of a page the signed angle of the chord from its first to its last baseline anchor (degrees, positive
falls to the right), and the page's median over the qualifying lines (at least 4 located boxes, anchors spanning at
least 3 page median word widths, both endpoints baseline anchors; a box-centre fallback never contributes; the pages
whose paragraph lines are not all horizontal are unavailable). `coordinates='recorded'` is the pre-correction angle
(what the guide shows), `'flat'` the same chords after the stored page warp. The guide through the comparison origin,
`drift_guide(d, gain)`, has a measured slope and an illustrative intercept; `gain` amplifies the slope for display,
never the quoted angle. These angles mix the writing direction with camera rotation and page deformation; the flat
state removes what the text-derived warp removes (PITFALLS 16).

**Inline line split** (`split_lines`, `PairComparison.split`). Two lines, one of each page, pulled apart into a band
(A above B) with the earlier and later context moved above and below by shared offsets: a display-only vertical
translation that keeps sizes, x positions, spacing and within-line slopes, tagged frame `display`. The partner line
is the one with the nearest median baseline (`nearest_reading_line`); nothing searches for similar words. Scores are
computed on the untouched selections.

## Worked example

```python
from vmsspatial import compare

c = compare.Comparison()                     # the manuscript, the sensitivity bundle, 'auto' anchors (about 10 s)
print(c.describe())                          # 227 pages, 37,478 units, anchors auto, policy sensitivity, data 2026-10-31

pair = c.pages('f20v', 'f21r', cutoff=3, align='starts')      # two openings, flat coordinates
print(pair.describe())                       # cutoff, alignment, frame, warp, anchors, the scores, the data version
pair.scores()                                # {'dice': 0.67, 'local_segment_similarity': 0.26, 'nearby_similarity': 0.49, 'units_a': 28, 'units_b': 24}
for seg in pair.segments():                  # connected groups: text_a, text_b, similarity, edits, lines_a, lines_b, clean
    print(seg['text_a'], '|', seg['text_b'], round(seg['similarity'], 3))
pair.lines()                                 # line 1 vs 1, 2 vs 2, 3 vs 3 without realignment
geo = pair.overlay_geometry()                # both pages' boxes in the common frame, tagged frame/warp
pair.split(0)                                # line 1 of A and its nearest partner pulled apart (display frame)
pair.drift()                                 # both pages' pre-correction drift indicators
ax = pair.plot()                             # the matplotlib overlay (pair.plot(mode='side'); plot.plot_pair(pair, drift=True))
pair.to_json('f20v_f21r.json')               # settings, scores, lines, segments, geometry, drift

sheet = c.bifolia('C:20-21', 'B:10-15', face='inner', cutoff=3)
sheet.joint                                  # equal-page mean and weaker-page minimum (mean Dice 0.597, direct 0.213, nearby 0.454 with glyph anchors)
comp = c.composite(['f30r', 'f37r', 'f16r'], align='page')    # whole pages to their opening anchors
comp.pairwise(); comp.plot()

ranked = c.rank(pool='herbal_a')             # Records: ranked[0]['a'], ranked.meta['eligible_pairs'], ranked.describe()
ranked.to_csv('herbal_a_pairs.csv', top=50)
c.rank(scope='both').meta['sheets']          # 35 sheets with all four slots complete

c.drift('f21v')                              # {'angle': -0.89, 'n': 7, 'lines': [...], 'unavailable': None, ...}
c.layout('f75r')                             # breaks, paragraph ends, envelopes in one frame
c.wheels('fRos')                             # the nine wheels translated to a common centre (display frame)
```

`Comparison(baseline='glyph')` reproduces the October 2026 workspace's anchors. The same functions exist unwrapped
(`load`, `select`, `measure`, `details`, `per_line`, `compare_sheets`, `rank_pairs`, `page_drift`, `split_lines`,
`layout`, `orders`); `tests/test_compare.py::test_documented_example` runs this example.

From the command line: `vmsspatial compare f20v f21r --cutoff 3 --details`, `vmsspatial compare C:20-21 B:10-15 --face
inner --cutoff 3`, `vmsspatial compare herbal_a --rank --top 10`, and `vmsspatial plot f20v --compare f21r --cutoff 3
--drift --out pair.png` (docs/PLOTTING.md).

## Web page

`viewer/compare.html` is the atlas's comparison page (Compare in the site menu). It reads `viewer/data/compare/` and
the manuscript bundle's words, computes every number in the browser with `viewer/js/compare_math.js`, and keeps its
whole state in the address, so every view is a link: `compare.html#a=f20v&b=f21r&cutoff=3&words=1`. The visible
controls and the call each one stands for:

| control (where) | address key | API |
|---|---|---|
| A, B pickers with ‹ › and Order (toolbar) | `a`, `b`, `order` (bifolia, the default: a sheet's pages together; folio: the page sequence; path1) | the folios (or sheet ids) passed to `select`; `orders()` for the lists |
| Step (toolbar) | `step` = bifolio, paragraph (page is the default, left out) | how far the A, B and Both arrows move. Bifolio goes to the same slot of the next sheet. Paragraph goes to the next paragraph on the page, then the first paragraph of the next page that has any, and sets Text to Custom. Page scope only: in bifolia scope the arrows move sheets |
| Both ‹ › (toolbar) | moves `a` and `b` together | steps both along the current Order, keeping the gap between them and wrapping at the ends; in bifolia scope it steps sheets |
| View switch (toolbar) | `view` = overlay, side, composite, segments, matches, wheels | `measure` + `details` on one frame; `plot_comparison(mode='side')`; `Comparison.composite`; `details`; `rank_pairs` / `rankings.json.gz`; `wheels.centered_layout` |
| Text: Whole page, Top 1 to 5, Custom (toolbar) | `text` = page (default), 1..5, custom; in Custom also `blocka`, `blockb`, `cutoff` | Whole page = `select(..., block='page', cutoff='all')` on both pages; Top N = `block='opening', cutoff=N` on both; Custom = the Block A, Block B and Lines choices in Settings (changing one of them switches Text to Custom; a preset resets all three) |
| Fit, +, −, wheel zoom and drag (toolbar, figure) | `zoom` = x,y,w,h of the view box | display only; 0.25x to 40x, Fit frames every box of the view (all pages of a composite, all wheels). The zoom holds when the pages change, at the same scale and place; a new view, panel count, Expand all lines, Scale or Alignment returns to Fit |
| Show words (toolbar) | `words=1` | the units' texts (`plot_pair(labels=True)`) |
| Boxes (toolbar) | `boxes` = outline, hidden (Filled is the default, left out) | Display only, the same control and key as the atlas. Hidden boxes still answer to hover and clicks, and the colour modes then paint the words; the scores do not change |
| Word direction (beside Show words, on pages with turned text) | `wdir` = ring (default, leave out), level | Display only. Bottom to centre turns each ring word with its bottom towards the wheel's centre and rotated lines along their chord; Level stands the same words upright. Both size a word by its length along its own direction, so the words at 3 and 9 o'clock are as large as those at 12 o'clock. Level text keeps its box fit. `viewer/js/word_labels.js` |
| Colour: Pages, Overlap JS, Overlap similarity, Shared area (toolbar) | `color` = pages (default), js, sim, area | computed live per scored box against the boxes of the other page that intersect it: `js_distance(line_features(word).joined, line_features(touching words).joined)`, the best `similarity(atoms, atoms)` among them, or the union of the intersections over the box's area; the palette spans the 5th to 95th percentile of the boxes in view, a box nothing touches keeps a grey outline, the value is in the tooltip |
| click a page's name or swatch above the figure | `hide` = a, b or folios, comma-separated | display only: that page's boxes are not drawn, the scores keep both pages, the status line says what is hidden |
| Show drift guide (toolbar) | `drift=1`; Settings: Guide slope `gain` = 1, 5, 10 | `page_drift(folio, coordinates)` for the page value and the per-line chords; `drift_guide(d, gain)` for the line through the origin |
| Paragraph bars in the left margin, beside each page's line labels | none | display only: `blocks` p1, p2 of the page; the number at the top of a bar is the paragraph's number on the page, shown in wide panels; narrow bifolia panels keep the bars. Labels and ring text are in no paragraph |
| Expand all lines (toolbar, Overlay and Top matches) | `expand` = 1 | display only: every panel stacks each line of both pages once, in reading order, in bands. A line and its partner share a band when each is the other's nearest by baseline; a line with no such partner stands alone. Sizes, x positions and within-line slopes do not change, words show in the bands, and rings, rays and other non-horizontal text keep their shape together below the bands. The scores stay those of the untouched selections. Lines cannot be opened one at a time while this is on; those already open return when it is off |
| ⤢ on a panel, when there is more than one; ⤡ Back to all, or Escape | `max` = the panel's position, from 0 | display only: that panel takes the full width with no height limit, framed on its own pages. The scores below still cover every panel, the arrows keep it maximized, and a line opened in it stays open when you return. Escape closes the panel's open line first, then returns |
| click a line label (A1, B1, in the gutter on the left) or a word; ‹ › and Close in the bar above the figure; Escape | `lines` = i,j[,k], several joined by `;` (0-based line indices of A and B, and the panel in bifolia scope) | `split_lines(a, b, (i, j), scale, limit)`; the partner is `nearest_reading_line` by median baseline; the scores stay those of the untouched selections. Works in Overlay and Top matches in both scopes, one comparison per panel, so every panel of a bifolia view can hold its own; a click in Side by side opens it in Overlay. Moving pages keeps each comparison (the A, B and Both arrows in any Step, and Previous and Next match): the line stays on the page that stays, or on A when both move, at its number or the nearest one the page has, and the other page takes the partner a click would give. A page with no lines shows none, and the line returns on the next page that has one. Picking a page from a list closes it. A block with no box on its first line is aligned on its first located line and is not scored |
| Segments: click a word, or a row of the groups table | `seg` = a:id or b:id | `details(a, b)`: `direct` (overlapping boxes), `nearby` (best box within reach), `connected` (the groups table) |
| Top matches: list, ‹ Previous match, Next match › | the list follows `a` (pages) or `face` (bifolia); stepping sets `b` | `rankings.json.gz` = `rank_pairs(first_line_scan(...))`, top 50 per page and per face; Settings: Ranking (`metric` = both, dice, js, spatial) re-sorts those 50 |
| Composite: chips with ×, Add | `pages` = comma list (default A and B) | `Comparison.composite(pages, align=...)`; pairwise Dice under the figure |
| Wheels: chips with ×, Add, the Zodiac / Astronomical / Cosmological shortcuts, Rings, Labels | `pages` (default A), `rings=0` hides the fitted circles, `labels=1` adds the nearby labels | `wheels.json.gz`, every wheel of every listed page translated to the common origin (`centered_layout(pages=[...])`), one colour per page; a display transform |
| Settings: Alignment | `align` = starts, page | `select(..., alignment='starts' / 'page')` |
| Settings: Coordinates | `coords` = flat, recorded | `select(..., coordinates=...)`; the drift guide follows |
| Settings: Scale | `scale` = pixels, body | `select(..., scale='pixels' / 'body_height')` |
| Settings: Scope, Face | `scope` = pages, bifolia; `face` = inner, outer, both | `sheet_rows` / `compare_sheets`: one panel per slot, equal-page mean and weaker-page minimum (`joint`) |
| Settings: Block A, Block B, Lines | `blocka`, `blockb` = opening, page, p1.., l<i>; `cutoff` = 1..5, all (written only in Custom) | `select(..., block=..., cutoff=...)` per page (`page_blocks` lists the blocks) |
| Settings: Export JSON | — | the same record as `PairComparison.to_json` (settings, scores, per-line table, connected segments, both geometries, drift) |

The metrics readout under the figure shows `measure` (Dice, direct-overlap and nearby EVA similarity, boxes scored)
and the joined-line JS distance of the two blocks' texts (`js_distance(line_features(text).joined)`); for bifolia the
joint mean and minimum per score. The defaults (overlay, whole pages, flat, block starts, page colours, words and
guide off) are `Comparison.pages(a, b, block='page')`; `text=3` gives the `cutoff=3` call of the worked example. An
expanded atlas page links here with its folio as A ("Compare this page").

## Data for other viewers

`vmsspatial viewer-data` writes `viewer/data/compare/`: `pages.json.gz` (per page the units with token ranges,
recorded rectangles, flat shifts and anchors, the lines, blocks, breaks and the drift indicator in both states),
`wheels.json.gz`, `orders.json` and `rankings.json.gz` (the top 50 pairs per page and per bifolium face). Field by
field: the `fields` key of each file and `viewer_data.COMPARE_FIELDS`. `compare.pages_from_viewer` reads the compact
records back in Python; `viewer/js/compare_math.js` (`selectUnits`, `measure`, `details`, `pageDrift`, `splitLines`,
`rankRows`) computes the same numbers in the browser.
