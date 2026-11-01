# vms-spatial

Two-dimensional spatial analysis of the Voynich manuscript text on its recorded word rectangles, and a viewer to look at the results.

**Live viewer:** https://eo777.github.io/vms-spatial/

The manuscript's words have positions: the Voynichese Project recorded a rectangle for every word on every page. This project puts the text (the ZL transliteration, read in a fixed bifolium order) onto those rectangles and asks spatial questions of it: which words are in view of a given word, how diverse they are, whether the next word tends to repeat what stands above or to the left of it, how lexical diversity falls across pages and sheets. It ships

- **an analysis toolset** (`vmsspatial`, Python): the manuscript and its physical structure, the page geometry, the source-pool selector and per-token measures, repetition outcomes and the statistics that compare them, layout-preserving shuffles, control texts (Markov chains, natural prose, saved generator streams) typeset into the manuscript's own lines, and the alignment review that decides which words have a usable position;
- **a visualization toolset** (`viewer/` + `js/`, static HTML and JavaScript): the heatmap of per-word measures on the recorded rectangles, rows as bifolia, leaves or pages, the manuscript by bifolium (the default), the page sequence or Path 1 order, an inspector for a word's window or its weighted spatial sources and cone, and the alignment review page. The viewer reads plain JSON bundles that the toolset writes, so other viewers can be built on the same data.

The Python measures reproduce the viewer's JavaScript to 1e-13 on every token (see *Numbers to check*).

**Defaults.** The toolkit's defaults are the correct and complete choice for anyone, not the shape of our own
studies. `Manuscript.load()` is the whole recorded manuscript: all 227 pages and every locus the Voynichese
Project recorded plus the Rosettes (paragraph text, labels, circular and radial text; 5,365 lines, 38,876 readable
tokens), read by bifolium: the manuscript's sheets by first leaf, each sheet's pages together (f1r, f1v, f8r, f8v, f2r,
...). `order='folio'` is the true page sequence (f1r, f1v, f2r, f2v, ...). Every line carries its ZL locus type and orientation. `load_bundle()` returns
it in the flat warp state: the page warp of the photograph (the curvature and tilt a page's lines share) is removed with the
shipped page warp product, because nobody should measure a vertical position in the recorded frame without asking
for `warp='recorded'`. Baselines default to `'auto'`: the ink baseline measured on the Beinecke scans where a page
has clean ink records, the glyph-corrected box baseline elsewhere, never the box bottom. Line statistics read
horizontal lines and report what they skipped. The October 2026 studies used a narrower shape, which stays
available by explicit option: `Manuscript.load(pages='paragraph', order='path1')` (the paragraph text of 207 pages
in the Path 1 order) and `load_bundle(policy, pages='paragraph', order='path1', warp='recorded')`; the tests guard both
shapes.

Poetry controls can retain their own source lines through the existing native-line typesetter: `python -m vmsspatial.poetry verses.json --out control.json.gz`. The importer recognizes the Towneley *Creation* and Latin *Aeneid* sources named by Timm (2016); short texts are never repeated to fill a page template. See [Poetry controls](docs/POETRY.md) for source import, native versus reflow placement, wrapping audits and comparison rules.


Independent poetry pages can preserve every source line without using Voynich frames: `python -m vmsspatial.verse_layout verses.json --out control.json.gz`. Page capacity, word gaps, line pitch, indentation and bounded dispersion are configurable; lines never wrap or justify. See [Independent verse pages](docs/INDEPENDENT_VERSE_LAYOUT.md).


For compact article figures using the actual manuscript image, `vmsspatial.illustrations.export_overlay` exports a registered crop, inspectable polygons, and a self-contained SVG from the boxes supplied by your analysis. See [Article image overlays](docs/ARTICLE_OVERLAYS.md).

**Left out of the word stream.** 150 of the 39,026 ZL tokens hold an uncertain glyph (`?`). They are not in `Manuscript.load()` or the bundles, so they count in no statistic and draw no box in the viewer, and 20 short loci that hold nothing else go with them. The alignment review keeps all 150, 128 of them with a box under the sensitivity policy. Separately, 159 of the 38,484 tokens on pages with rectangles have no usable box; `coverage_by_page.csv` gives each one's reason.

## Quickstart

```
git clone https://github.com/eo777/vms-spatial && cd vms-spatial
python -m pip install --upgrade pip    # installing from pyproject.toml with -e needs pip 21.3 or newer
pip install -e .[plot]                               # numpy; matplotlib for the renders
python -m vmsspatial verify-data                     # every shipped data file against its SHA-256
python -m vmsspatial plot f75r --out f75r.png        # a page: its word rectangles and baselines, flat state
python -m vmsspatial compare f20v f21r --cutoff 3    # two openings overlaid: Dice, direct-overlap and nearby EVA similarity
python -m vmsspatial plot f20v --compare f21r --cutoff 3 --out pair.png
python -m vmsspatial viewer-data && python -m http.server   # then open http://localhost:8000/viewer/ (the atlas)
```

```python
from vmsspatial import Manuscript, load_bundle, compare, wheels
ms, app = Manuscript.load(), load_bundle('sensitivity')          # 227 pages, every locus; the flat warp state
c = compare.Comparison()                                         # the comparison toolkit (docs/COMPARE.md)
pair = c.pages('f20v', 'f21r', cutoff=3)                         # two openings overlaid; pair.describe()
pair.scores(); pair.segments(); pair.lines(); pair.plot(); pair.to_json('pair.json')
c.rank(pool='herbal_a').to_csv('herbal_a_pairs.csv')             # the ranked first-line pairs
wheels.load_wheels()['summary']                                  # 35 wheels on 26 pages (docs/WHEELS.md)
```

## Install

```
git clone https://github.com/eo777/vms-spatial
cd vms-spatial
python -m pip install --upgrade pip    # installing from pyproject.toml with -e needs pip 21.3 or newer
pip install -e .                # numpy only; matplotlib for the page renders, pytest for the tests, pip install -e .[images] for the ink measurements
python -m vmsspatial verify-data
```

The repository carries the data (`data/`, about 33 MB: the transcription, the physical map, the word rectangles with their alignment review, the control texts and generator streams; `viewer/data/` is the viewer's build of it), so a clone works at once. `vmsspatial verify-data` checks every file against the SHA-256 manifest (`vmsspatial/resources/data_manifest.json`); `vmsspatial fetch-data` refreshes the shipped files from their published copies (see *Optional files* for the rest). Each release is a tagged commit, and the data folders are marked binary in `.gitattributes`, so they never render as diffs. `VMS_SPATIAL_DATA` points the toolkit at another data folder. Python 3.9 or newer; Node.js for the viewer tests and the JavaScript reference scorer.

### Optional files

Not in the repository, and not needed to use the toolkit: the inputs the alignment review was built from (group `raw`:
the Voynichese Project's 225 XML pages, the frozen page-wise alignment, the site's coordinate inventories), two files of
the October 2026 studies (`model`: the positional composition model whose bifolium order is `resources/path1_order.json`;
`reference`: the component-impact study's per-token table) and the full-resolution Beinecke scans (`images`). The
manifest lists each as optional with its published URL or its path in the research workspace: `vmsspatial fetch-data
--group <name>` downloads those with a URL, `fetch-data --from-workspace --group <name>` copies any of them from a
workspace (`VMS_WORKSPACE`), and `paths.resolve(key)` finds one in either place when a local analysis wants it. The
publisher never ships an optional file, even when it has been fetched, so a clone stays at the shipped set.

**Data model.** Every coordinate-bearing table (a bundle, a baselines table, the ink product, an overlay) carries
three tags, `frame` (recorded; detected for the Rosettes), `warp` (recorded or flat) and `source` (voynichese,
beinecke, display, synthetic, detected), and `frames.require_same` refuses to combine two tables that differ in frame
or warp. The page warp, the registrations and the baselines are shipped data products (`page_warp.json.gz`,
`registrations.json.gz`, `baselines.json.gz`); `load_bundle(policy, warp='flat')` or `warp.flatten_bundle` apply the
stored warp and `warp.transform` moves any table with it, so no study fits its own. Every line carries an orientation
record (horizontal, rotated, circular, radial, label) and the line statistics read horizontal lines by default.
[docs/DATA_MODEL.md](docs/DATA_MODEL.md) has the frames, the products, the invariants and the one-call recipes.

**Before scoring anything, read [docs/PITFALLS.md](docs/PITFALLS.md):** the word-length trap of the selector, the pool-size confound, edge words, shuffles that must re-typeset, baselines that must match the observation's geometry, and the other lessons of the October 2026 reviews, each with the function that answers it.

## Analysis quick start

```python
from vmsspatial import Manuscript, load_bundle, SpatialContext, PoolSpec, STUDY_SELECTOR
from vmsspatial.measures import Features, score
from vmsspatial.outcomes import outcomes, token_meta
from vmsspatial.stats import quintile_contrast

ms = Manuscript.load()                 # 52 bifolia, 227 pages, 5,365 lines, 38,876 tokens by bifolium (every locus)
bundle = load_bundle('strict')         # words, lines, reviewed word rectangles (flat warp state), glyph components
# the 2026 studies' shape: Manuscript.load(pages='paragraph', order='path1'); load_bundle('strict', pages='paragraph', order='path1', warp='recorded')
ctx = SpatialContext(bundle)           # per-page centres, median word width, line pitch

pool = ctx.pool(31343, STUDY_SELECTOR) # the words in view of token 31343: 3 word widths left, cone 8 lines up, 45 deg
table = score(ctx, STUDY_SELECTOR)     # per-token: components, h1, h2, worddiv, js, n, ess, available ...

node, group, bstart, bend = token_meta(ms, ms.line_words())
out = outcomes(bundle['words'], bstart, bend)                       # app_impact, arrival, repeat, departure, full
mask = out['full'] & (table['components'] == table['components'])   # complete windows inside the bifolium, valid score
print(quintile_contrast(table['components'], out['app_impact'], node, mask))
```

From the command line:

```
python -m vmsspatial info
python -m vmsspatial score --out scores.csv                      # every token's pool measures and outcomes
python -m vmsspatial score --spec "left=0,depth=8" --policy sensitivity
python -m vmsspatial contrast                                     # the within-bifolium contrasts, three controls
python -m vmsspatial shuffle-check --out outputs/layout           # typesetting of the layout-preserving shuffles + f75r, f33v renders
python -m vmsspatial control markov:section --out markov.json.gz  # a control text as a bundle
python -m vmsspatial viewer-data --control markov:section --control stream:timm_spatial
python -m vmsspatial audit check | summary | flagged --out flagged.csv | token f75r.42@32:39 | page f75r
python -m vmsspatial audit coverage                              # coverage_by_page.csv: located tokens per page and locus type
python -m vmsspatial orientation                                 # lines and pages by orientation kind
python -m vmsspatial build-products                              # registrations, baselines table, page warp (docs/DATA_MODEL.md)
python -m vmsspatial realign --out review.json.gz                # align the ZL tokens to the rectangles, word by word (needs the raw XML group)
```

`scripts/` holds worked analyses: `component_contrast.py` (the pool-diversity contrast on the manuscript and three copier streams), `residual_check.py` (the contrast under the joint length and pool-size control against 19 size-matched re-typeset shuffles), `direction_and_regions.py` (cone above against the mirror below, lines-only pools, a custom region), `mattr_route.py` (MATTR by group and bifolium with the bag and clustering split), `make_controls.py` (every standard control bundle plus the viewer data).

## The viewer

```
python -m vmsspatial viewer-data          # writes viewer/data: the manuscript bundle, the layout record, the index
python -m http.server                     # from the repository folder (the pages fetch their data; file:// does not work)
```

Open `http://localhost:8000/viewer/`. The atlas page: **Text** (any bundle in `viewer/data`), **Order** (Manuscript bifolia, the default: the sheets by first folio, each kept together; Manuscript pages; Path 1 bifolia), **Colors** (plain boxes, or a measure: MATTR, repeated spellings, word repetition impact, step change, source edit distance and candidates, component diversity, H1, H2, JS distance, and the group *Lines, baselines and warp*), with a Configuration section that shows the chosen measure's controls, **Coordinates** (Recorded, the default, or Flat: the boxes and overlays without the page warp; the measures stay flat either way, and a page image brings the boxes back to recorded coordinates while the choice stands; `coords=flat` in the address). Click a word for its window or its weighted spatial sources and cone; expand a page for the Voynichese image, word labels and box outlines. `alignment.html` is the review page: every ZL word's assignment, its flags and the original rectangles on the native image.

`sections.html` lays every page of a section or Golf group over each other: paragraph polygons, paragraph starts and ends, annotated breaks, and a heatmap of where the pages have text, each layer with its own opacity slider ([docs/SECTIONS.md](docs/SECTIONS.md)).

`stream.html` runs whole pages in a chosen order: a chain of bifolia with four pages to a row, one continuous column, or laid over each other. Restore each page's recorded tilt, drag how far each bifolium overlaps the last, reorder sheets, keep named boundary sets, and export every page's angles and margin points as JSON ([docs/STREAM.md](docs/STREAM.md)).

`search.html` lights up the words that match a pattern on every bifolium at once: small tiles of all the sheets, up to six patterns in their own colours, any order of sheets, with counts and shares beside them and each page opening on its image. Patterns use the Echo rule builder's language: globs, AND, OR, NOT, neighbour offsets and positions on the line, paragraph and page ([docs/SEARCH.md](docs/SEARCH.md)).

`compare.html` is the comparison page: two pages (or two bifolia, face by face) laid over each other on their word rectangles after one translation, whole pages or the top lines, with the Dice, direct and nearby EVA and JS scores, live per-box colours (overlap JS, overlap similarity, shared area), an inline reader for any pair of lines, the drift guide, side-by-side and composite views, the word-segment correspondences, the ranked first-line matches and the centred wheels of one or many circular pages. Every view is a link, for example `viewer/compare.html#a=f20v&b=f21r&color=js&words=1` (the controls and their API calls: [docs/COMPARE.md](docs/COMPARE.md), *Web page*).

*Lines, baselines and warp* paints how each line lies on the page. Per word: the residual from the chord and from the least-squares line, the warp shift removed, the ink baseline against the box bottom and against the glyph baseline, the ink x-height, the intrusion depth. Per line: the chord angle flat, recorded and centred on the page, the fit angle, the end offset (signed, centred, absolute), the fit RMS, sag, jitter, the largest jump share, accumulation rho, the position of the largest residual, the break step and count, the ink angle against the boxes, the x-height spread, the located words and the span. Per page: the warp amplitude, tilt, keystone and whether a field was fitted. The overlays on an expanded page draw the chords, line fits, baseline anchors, the page warp, breaks, component fits at breaks, intrusions and ink fits in the state shown, one or several at once; clicking a word opens its line's notes. The same numbers come from Python: `vmsspatial.line_stats.line_table()` and `word_table()` return records with `to_csv`, `plot.plot_page(folio, color_by=<key>)` paints any key, and `line_stats.KEYS` gives every unit and sign ([docs/PLOTTING.md](docs/PLOTTING.md), *Line statistics*). They are computed on the sensitivity geometry, so a shared box has its value in the strict atlas bundle too.

To build another viewer, read `viewer/data/index.json` (the bundles), `layout.json.gz` (page sizes, bifolia, orders, section labels, scopes) and a bundle:

| key | content |
|---|---|
| `words` | every token in stream order |
| `lines` | `{page, locus, bifolium, start, end}` contiguous token ranges |
| `geometry` | `[x0, y0, x1, y1]` or null per token, in the XML pixel frame of the page |
| `components` | `{word: [units]}` glyph units (Zattera) or letters |
| `spatialReview` | manuscript bundle only: the review records (assignment groups, flags, eligibility) |

**Bring your own measures to the atlas.** A study does not copy the viewer: `viewer_data.study_data(out_dir, bundle,
key, label, measures={...}, overlays={...}, line_notes=[...])` writes a data folder holding one bundle (the words, lines
and boxes the study scored) with its own per-token measures (`measure`, or `per_line` to broadcast per-line values, or
`line_measure` for one value per line), its overlays (lines and markers in page coordinates, `overlay` / `overlay_item`: chords, fitted baselines, break
markers, with `points_flat` beside recorded points) and per-line notes, plus an `index.json` that names the toolkit's layout and review files by path or URL.
Opening `viewer/index.html#data=<url of that folder>` shows the measures under Colors ("From this text"), the overlays
on an expanded page (following the Voynichese image when it is shown) and the notes when a word is clicked; a link can
name the view (`&colors=m:<key>&expanded=<folio>&line=<locus>&overlays=all&image=1`). A per-line statistic broadcast
to its words is declared `per='line'` so that row means weight lines, not words.

`viewer/atlas.js` turns a bundle and the layout into the rows (pure functions, also run by the node tests); `js/sources.js` (the selector and the pool measures), `js/heatmap_math.js` (windows, impact, step change), `js/copy_math.js` (edit distances) and `js/review.js` (review labels and native boxes) are standalone and used by both the viewer and `js/measure_cli.js`, the command-line reference scorer.

### Extra pages and the Rosettes

The study text covers the paragraph text of 207 pages. `Manuscript.load(extra=True)` and `load_bundle(policy,
extra=True)` add the 20 circular and astronomical pages the Voynichese Project recorded (f57v, f65r, f67v1, f68r3,
f68v1, f69v, f70r1, f70v1, f70v2, f71r-f73v, f116v), every page's labels, circular and radial loci (all 38,876
readable tokens of the 227 pages, each line with its ZL locus type and orientation record) and the Rosettes foldout's
labels and circular texts, whose word
positions the toolkit finds on the Beinecke scan and links to the transcription (`vmsspatial.segment`,
`vmsspatial.rosettes`, `scripts/rosettes_geometry.py`; method, confidence and limits in [docs/ROSETTES.md](docs/ROSETTES.md)).
Detected positions carry a confidence and the geometry kind `detected`; they are never mixed silently with recorded
rectangles. The viewer shows all 227 pages by default (`vmsspatial viewer-data`; `--no-extra` for the study pages only).

## Comparison

`vmsspatial.compare` lays the text block of one page over another's with one translation and nothing else and
reports the occupied-area Dice on the exact rectangle unions, the direct-overlap EVA similarity (each box against the
joined atoms of the boxes that overlap it by a fifth of the smaller area, both directions, weighted by the shared
area), the nearby EVA similarity (the best single match within half a body word width and half a body box height),
the per-line table and the word-segment correspondences. Selections are a block of a page (the opening = the first
five paragraph lines, the whole page, a canonical paragraph, a single locus), a line cutoff (top 1..5 or all), a
coordinate variant (`flat`, the stored page warp removed with the baseline anchors moved by each box's shift, or
`recorded`), an alignment (`starts`: the block's first box's anchor is the origin;
`page`: the page's opening anchor is the origin and later paragraphs keep their page positions) and a scale (pixels
or body height). Bifolia are compared face by face (inner = A verso beside B recto, outer = B verso beside A recto)
with the equal-page mean and the weaker-page minimum. `first_line_scan` / `rank_pairs` rank every eligible page pair
(20,100) or bifolium face pair (inner 703, outer 741, all four slots 595) by the worse of the Dice rank and the
Jensen-Shannon rank of the opening lines, or by the position-constrained EVA similarity. The scores describe
resemblance after a translation; they do not test copying (PITFALLS 25). The circular text has its own product:
`vmsspatial.wheels` fits every ring's circle, screens it, groups coincident rings into 35 wheels on 26 pages and
ships them (`data/manuscript/wheels.json.gz`); the orientation records take their centres from it, and a centred
composite of wheels is a display transform in the frame `display`, not measured geometry (PITFALLS 24).
[docs/COMPARE.md](docs/COMPARE.md), [docs/SECTIONS.md](docs/SECTIONS.md), [docs/WHEELS.md](docs/WHEELS.md), [docs/PLOTTING.md](docs/PLOTTING.md).

```python
from vmsspatial import compare
c = compare.Comparison(baseline='glyph')                         # the October 2026 workspace's anchors ('auto' is the default)
pair = c.pages('f20v', 'f21r', cutoff=3, align='starts')         # pair.scores(), pair.segments(), pair.lines(), pair.overlay_geometry(), pair.split(0), pair.plot(), pair.to_json(path)
c.bifolia('C:20-21', 'B:10-15', face='inner', cutoff=3).joint    # equal-page mean and weaker-page minimum
c.composite(['f30r', 'f37r', 'f16r'], align='page').plot()       # several pages to their opening anchors
c.rank(pool='herbal_a').to_csv('herbal_a.csv')                   # the first-line retrieval order as records
c.drift('f21v')                                                  # the pre-correction drift indicator (median signed line chord angle)
```

The workspace's two late additions are in the kit too: the pre-correction drift indicator (`compare.page_drift`: per
line the signed baseline chord angle, the page median, recorded and flat; the viewer data carries both) and the inline
line split of the overlay (`compare.split_lines`: a display-only vertical translation, frame `display`).

The atlas ships the comparison data for its own comparison page (`viewer/data/compare/`: units with recorded
rectangles, flat shifts and anchors, blocks, break markers, the wheels, the orders, the pair rankings; 1.1 MB
gzipped) and `viewer/js/compare_math.js`, the same metrics in JavaScript, checked against the Python results on 30
saved pairs to 1e-9.

### GitHub Pages

The repository root `index.html` forwards to `viewer/`, so enabling Pages on the main branch serves the atlas at
`https://<user>.github.io/vms-spatial/`. The viewer reads `viewer/data/` (in the repository) and the Voynichese
Project's images from voynichese.com; the Rosettes image is the toolkit's quarter-scale copy in `viewer/img/`.

## The analysis toolset

| module | what it holds |
|---|---|
| `manuscript` | `Manuscript.load(order)`: nodes (bifolia), pages with their physical record, lines; orders `bifolia` (the default), `folio` (the page sequence), `path1`; `bifolium_ranges` (a sheet's token ranges in any order); `tokenize`, `transitions`, Golf group labels |
| `bundle` | the bundle structure; `load_bundle(policy)` with `strict` or `sensitivity`; `make_bundle` for any text with any geometry |
| `geometry` | line frames from the rectangles (oversized boxes, drawing gaps, vertical gaps), `place_in_slot`, `fill_slots`, `synthetic_geometry`; `PageGeometry` + `Layout` for word-by-word placement with the pool in view |
| `selector` | `PoolSpec` (direction, left/right reach, depth, angle, apex offset, weights, centre or edge distance, cap), `SpatialContext.pool`, `candidates` + `Region` masks + `select` for any region, reading-order windows |
| `measures` | `Features`, `measure` (worddiv, h1, h2, components, js, n, ess), `score`, `score_window`; MATTR, bag expectation, rolling series, bifolium means, group tables |
| `outcomes` | app impact, arrival burden, repeat, departure, the full `word_impact` (windows, affected, gain, step change) |
| `stats` | within-bifolium quintile contrasts, stratified contrasts (length, pool size, both), leave-one-bifolium-out fit, joint regression, paired contrast, shuffle rank, interior cohorts |
| `shuffles` | size-matched word shuffles inside paragraphs/pages/bifolia/all, line shuffles with fitted letter size, reversed and rotated lines, all re-typeset; `repeated` for shuffle baselines |
| `controls` | generator streams, Markov chains (whole, Currier, section) and natural prose, every one typeset into the manuscript's line frames at the line's letter size and checked (`build_control`); `markov_box` / `prose_box` are flagged diagnostics of the one-word-per-box error |
| `layout_check` | carry-over, missing boxes, overlaps, box-width error, page renders |
| `audit` | flags and policies, the review (geometry per policy, per-token tables and descriptions), the invariant checks |
| `images` | the page images: the Yale IIIF index of the Beinecke scans, the image cache outside the repository, the registration of the recorded frame to each image (display affine; SIFT + RANSAC homography with per-line local shifts for the scans), `region` with the inverse mapping |
| `ink` | ink measurements on the page images: binarization, per word the extent, writing angle, x-height band, ascender and descender, per line the robust baseline fit; the data product `ink_measures.json.gz`, `load_ink`, `intrusions`, `gap_table` |
| `compare` | the comparison model: units, blocks, selections (cutoff, coordinates, alignment, scale), the overlay scores (Dice, direct-overlap and nearby EVA similarity), segment correspondences, per-line table, bifolium faces and the joint value, the first-line scan and the pair rankings, paragraph layout features, orders |
| `wheels` | the circles of the circular text: ring fits with acceptance screens, complete-link grouping into wheels, the shipped product `wheels.json.gz`, the centred display transform (frame `display`) |
| `plot` | matplotlib renders (optional extra `plot`): a page with boxes, baselines, orientation and breaks, on the page image if asked; a comparison overlay; wheels; a bifolium face; `vmsspatial plot` |
| `line_stats` | one record per horizontal line and per located rectangle: chords and fits in both warp states, each word's residual, the warp shift, line shape, breaks, the ink baseline and x-height, intrusions (`line_table`, `word_table`, `KEYS`) |
| `viewer_data`, `viewer_measures`, `jsref`, `datafiles`, `cli` | the viewer's data (bundles, layout, the comparison extras, the atlas's line measures), the JavaScript reference from Python, the data manifest, the command line |

### Geometry and rules

Every synthetic layout uses one implementation: a line's frame is the horizontal extent and the median vertical extent of its recorded rectangles (oversized ones excluded), split into text segments at isolated gaps wider than twice the page's median word width and at vertical gaps shared by neighbouring lines (a plant stem, a column); words are placed left to right at the line's letter size, follow the recorded line's drift, carry over to the next slot when they do not fit, and overflow below the page's lowest line.

The selector follows the viewer's `sourcePool`: on the same line, centres within `left` median word widths to the left; on earlier lines, rectangles that intersect the cone of `depth` line spacings above the target with half-angle `angle`; weight = alignment / (1 + distance)^2 or uniform; the heaviest `cap` kept. Two variants remove the selector's dependence on the target's own length: `metric='edge'` (`WIDTH_NEUTRAL_SELECTOR`, the same-line distance is the gap between the boxes plus one) and `target='cursor'` (`CURSOR_SELECTOR`, the window is fixed on a provisional box one median word wide at the target's left edge); both are in the viewer too.

The statistics come as one report: `stats.standard_contrasts` gives, for components, H2 and word diversity, the within-bifolium contrast raw, inside exact word length and inside length × pool-size tertile, on all words and on the interior cohorts; `shuffles.baseline` draws size-matched shuffles in the observation's own geometry (recorded rectangles kept, or re-typeset), and `stats.baseline_summary` reports the excess over the shuffle mean with its rank and one-sided permutation probability.

Geometry policies: `strict` is the reviewed word-level geometry (32,319 of the 34,977 tokens of the paragraph text located); `sensitivity` also admits shared and spelling-disputed locations as approximations (34,876 located). Line frames for typesetting are taken from the sensitivity geometry, the most complete reviewed one.

Baselines: a rectangle's bottom is a biased baseline, because descenders (y, m, q, l, g) push a word's bottom below the writing line and gallows (p, f, the pedestalled cph, cfh, cth, ckh, then t and k) raise its top, and a sloped word's axis-aligned box reaches its bottom at the down-slope end. `baselines.glyph_effects(bundle, ms)` measures those effects on the manuscript itself (a within-line regression of the box bottoms' and tops' residuals on the Zattera units in the word, in page median box heights) and `baselines.word_baselines(bundle, ms, 'glyph')` gives one baseline point per word from the corrected bottom and the corrected top plus the line's x-height, moved along the line's slope to the box centre and weighted by precision; `baselines.baseline_rms` compares `bottom`, `centre` and `glyph` by the within-line residual (on the manuscript 0.169, 0.149 and 0.129 H). What the boxes cannot give, a box drawn off the text's own angle and the ink's actual baseline, would need the page images.

Ink: the words' own baselines, x-height bands, angles and extents measured on the Beinecke scans (`vmsspatial.ink`; see *Ink measurements* below) give the baseline method `ink`, which the boxes could not.

Dewarping (flattening): the rectangles were drawn on photographs of a bound book, so a page's lines share a curve and a tilt that are not the scribe's. The toolkit removes them with a **robust, leave-one-line-out polynomial warp model with per-line fixed effects**, a description rather than an established name: one intercept and slope per line, one smooth polynomial field shared by the page's lines, a robust fit, and the field for each line taken from a fit without that line. [docs/DEWARPING.md](docs/DEWARPING.md) gives the model, its named parts, its parameters and its limits. `flatten(bundle, ms)` fits this per page from the text lines' baseline points (`baseline='auto'`: ink where clean, glyph otherwise) and returns a copy of the bundle with every rectangle moved vertically by the warp (`geometry_kind='flattened'`, the provenance extended, a per-page report with the tilt, keystone, curvature amplitude and its stronger side under `bundle['flatten']`). A page-wide slant the scribe wrote cannot be told from camera rotation and is removed with it; a line's deviation from the page's shared slope and its own bowing survive. The shared curvature is not identified as binding: its stronger side falls on the gutter side on about half of the pages, which is chance.

### The alignment review

`data/manuscript/spatial_review.json.gz` associates all 39,026 ZL tokens with the recorded rectangles: an assignment
group per word or shared box (the original rectangles, their union, the coordinate spellings, the native display
rectangles), a flag taxonomy (`vmsspatial.audit.flags`: shared boxes, cross-line merges, disputed spellings, layout
outliers and the rest) and two eligibility policies, `strict` (word-level assignments only) and `sensitivity` (shared and
disputed locations admitted as approximations). Assignments corrected or cut on the native image during the review are
already applied and carry the flags `alignment_corrected`, `alignment_reviewed` and `image_reviewed_boundary`; the file
is the data product, not a log of how it was made. `vmsspatial audit summary | flagged | token <id> | page <folio>`
describe it, and `audit check` verifies its invariants (no token lost or assigned twice, strict geometry only from
single-word or resolved assignments, the bundle agrees with it).

`vmsspatial.realign` makes the assignments word by word. The XML lists a page's words in its own order, so ZL is split
into streams by locus category (paragraph, label, circular, radial), each aligned in reading order with the XML words on
spelling; the line of each locus, read along its own direction (rotated blocks and rings included), then decides what
spelling cannot, because a repeated word or a single letter matches anywhere: a placement must lie on its line, in
reading order, or beside its located neighbours. Of the 38,484 tokens on pages with rectangles, 38,325 are located
(sensitivity) and 35,286 are word-level (strict). The other 159 each say why (`audit.flags`, the columns of
`coverage_by_page.csv`): `no_xml_word` 71 (the XML has no word there, the rare glyphs among them),
`transcriptions_differ` 53, `position_failed` 5, `invalid_box` 27 (the XML rectangle has no width), `disconnected_parts`
3 (the pieces of one word lie apart along its line). The 542 tokens of fRos and f116v have no recorded rectangles.

### Ink measurements

The boxes cannot give the ink's baseline or a box drawn off the text's own angle. `vmsspatial.ink` reads the ink on
the Beinecke Library's full-resolution scans (about 2,800 x 3,750 px a page, 2.5 scan px per recorded px) and ships
the result as the data product `data/manuscript/ink_measures.json.gz` (one record per located rectangle of the
sensitivity bundle, numbers only, 0.1 px; `ink.load_ink()`, `ink.unit_rows`, `ink.line_rows`).

*Registration* (`vmsspatial.images`). The recorded frame is the Voynichese Project's page image scaled, so the
display rectangles of the alignment review give an exact affine from the recorded frame to the display image
(`registration(folio, 'display')`, residual about 1 px from the display rectangles' rounding). For the scan
(`registration(folio, 'beinecke')`) SIFT keypoints of the display image are matched to the scan at one third scale
and a homography fitted by RANSAC (thousands of inliers on a text page; a similarity when they are few), composed
with the display affine; a local shift per text line, the median residual of the inlier matches around that line,
corrects what a single homography cannot, the two photographs' different page warp (a smooth quadratic field of the
residuals stands in for lines with few inliers). The record carries the matrix, the median reprojection error in
recorded px, the inlier count, the per-line shifts and quality flags; a page whose registration fails is flagged and
never measured. `images.region(folio, box, pad)` returns the mapped region of a rectangle in memory with the inverse
mapping back to the recorded frame. Registrations are cached as numbers in `<cache>/registration_<source>.json`.

*What is measured.* Per text line the image region around the mapped rectangles is binarized (Sauvola on the
luminance, window 1.5 H, saturated paint removed; components mostly outside a word's box are dropped as a
neighbour's ink or a drawing, a merge with a neighbour is flagged). Per word: the ink's horizontal extent; the
writing angle (shear angles within 6 degrees that make the vertical profile sharpest; words narrower than 2 H take
the line's angle); the x-height band from the sheared profile (the baseline is the strongest drop of the profile near
the box bottom, the mean line the lowest rise 0.28 to 0.8 H above it that heads a dense region holding most of the
ink; edges sub-pixel); the ascender top and descender bottom beyond the band with their x positions; coverage;
flags (little ink, paint, neighbour ink, poor registration, band not found, angle from the line, touch above or
below, short word). Per line: a robust straight fit through the word baselines (angle, offset, residuals), the median
x-height and its spread, the box least-squares and chord angles for comparison, and a box-to-ink cross-correlation
shift (a diagnostic of the boxes against the ink; it does not alter the registration). Everything is in the recorded
frame; `baselines.word_baselines(..., 'ink')` turns the records into baseline points (falling back to the glyph
baseline where a record is missing or flagged, and saying how many), `flatten(..., baseline='ink')` and
`baselines.baseline_rms` accept `ink`, and `ink.intrusions` lists the descenders that reach into the line below and
the ascenders that reach into the line above, with `ink.gap_table` giving every word's gap to the previous line.

*Images and cache.* No image or crop is stored in the repository or the data folder. `vmsspatial fetch-images
[--source beinecke|display] [--folios ...]` downloads the pages (sequentially, with a pause; a complete file is never
fetched twice) into `%LOCALAPPDATA%\vmsspatial\images` (`~/.cache/vmsspatial/images` elsewhere), or the folder
named by the environment variable `VMS_SPATIAL_IMAGES`; the 207 study pages take about 500 MB of scans and 20 MB of
display images. `resources/beinecke_iiif.json` is the index of Yale's IIIF manifest (213 canvases; every folio of
the toolkit maps to a canvas, 20 foldout folios to two candidates that the registration resolves by inlier count).
`vmsspatial ink-measure` rebuilds the data product. Images: Beinecke Rare Book and Manuscript Library, Yale
University (Beinecke MS 408), served by Yale University Library's digital collections; the Voynichese Project's
display images are loaded from voynichese.com.

*Limits.* The ink baseline is the bottom edge of the dense band, found per word; a word whose band is not found,
whose box holds paint or a neighbour's ink, or whose page registered poorly is flagged and left to the glyph
baseline. The x-height is the least certain measure (the band's top edge competes with risers and gallows loops).
The two photographs do not share a warp: say which image frame a number used (`docs/PITFALLS.md`, entries 18 and 19).

## Numbers to check

| what | value |
|---|---|
| manuscript, default (every page and locus, by bifolium) | 52 bifolia, 227 pages, 5,365 lines, 38,876 tokens |
| manuscript, study shape (`pages='paragraph', order='path1'`) | 50 bifolia, 207 pages, 4,130 lines, 34,977 tokens, 740 paragraph starts |
| tokens located, default bundle, strict / sensitivity | 35,613 / 38,605 of 38,876 (fRos 408 detected) |
| paragraph text located, strict / sensitivity geometry | 32,319 / 34,876 of 34,977 (all 39,026 ZL tokens: 35,286 / 38,325) |
| tokens without a usable box on pages with rectangles | 159 of 38,484: 71 no XML word, 53 transcriptions differ, 5 position failed, 27 rectangle without width, 3 pieces apart |
| Python vs JavaScript, study selector, every measure, 34,977 tokens | max abs difference 1.2e-13 |
| manuscript re-typeset into its own frames (sensitivity geometry, horizontal lines) | 797 carried, 310 without box (the 48 rotated lines are not typeset), 1,391 overlaps, none off by 1.5x |
| lines by orientation (sensitivity bundle, 207 pages) | 4,070 horizontal, 48 rotated, 12 without rectangles; all 227 pages and loci: 4,070 horizontal, 921 label, 83 circular, 141 radial, 48 rotated, 102 unknown |
| words shuffled in paragraphs, recorded boxes kept (superseded) | 40.7% of words in a box off by more than 1.5x |
| wheels of the circular text (sensitivity geometry, every page) | 35 wheels on 26 pages (12 Zodiac, 6 on 5 Astronomical, f68r2 two, fRos nine), 4 circular loci rejected, 2,216 accepted boxes |
| comparison: first-line scan | 205 pages scanned, 20,100 eligible pairs; bifolium faces inner 38 sheets / 703 pairs, outer 39 / 741, four slots 35 / 595 |
| line statistics, default bundle (`line_stats.line_table()`) | 4,070 horizontal lines, 4,043 with a chord, 3,987 with a fit; 37,478 located rectangles |
| the same on 3,773 lines of the study shape (paragraph text, 4 or more anchors over 3 word widths, outside the pages with rotated paragraphs) | median absolute chord angle 0.50 deg flat, 1.34 deg recorded; absolute end offset 0.18 H; line-median RMS 0.08 H; ink baseline 0.19 H above the box bottom (28,484 clean words) |

`python -m pytest tests` runs these (the slow ones take a few minutes; `-m "not slow"` for the quick set); `node --test viewer/test/*.test.js` the viewer's.

## Orders and the Path 1 caveat

The default is the manuscript by bifolium (`order='bifolia'`): the sheets by their first leaf, each sheet's pages
together. `order='folio'` is the true page sequence, panels included, so a sheet's pages lie apart. Path 1
(`order='path1'`) is the working order of the 50 bifolia from the positional composition model that the 2026 research
used; it is not an established chronology. Windows and MATTR follow the stream order of the bundle in use. A sheet is a
label on pages and lines, not a stretch of the stream: sheet statistics gather its words wherever they fall
(`measures.group_table`, the atlas's row means), `Manuscript.bifolium_ranges` gives its token ranges, and `mean_within`
takes those ranges. Every product is keyed by page and locus or by token id, so any order reads the same data.

## Publishing

`python publish/publish.py --dry-run` assembles the repository folder (`publish/site.json`: the toolkit tree with its data folders), refusing any file that carries a local path or exceeds GitHub's size limit; `--commit --push` releases it as an ordinary tagged commit (`site.json` has `"history": "keep"`).

## Attribution and license

Code: MIT (LICENSE). Word rectangles: The Voynichese Project, 2014, Apache-2.0; transliteration: ZL (Zandbergen and Landini); see NOTICE. No Voynichese page image is stored; the viewer loads them from voynichese.com on request. Page scans: Beinecke Rare Book and Manuscript Library, Yale University (Beinecke MS 408), via Yale University Library's digital collections (IIIF); the toolkit downloads them into a cache outside the repository and stores only numbers measured on them. The one image in the repository is the quarter-scale copy of the Beinecke Library's scan of the Rosettes foldout (`viewer/img/fRos.jpg`), on which the detected word positions are shown.
