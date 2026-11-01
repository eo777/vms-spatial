# Pitfalls of spatial word statistics, and the functions that answer them

The 26 to 28 October 2026 studies (the MATTR template-availability study and its two external audits) found a series
of ways to fool a spatial statistic. Each entry below names the trap, what it cost, and what in the toolkit prevents it.
Read this before scoring a new text or a new pool shape.

## 1. The selector reads the target's own length

**Trap.** With centre-to-centre same-line distance and inverse-square weights, the left neighbour's centre lies closer
when the target word is short. One same-line word then dominates the weighted pool of a short target (8 percent of the
pool's words carried 36 percent of its weight), pool diversity rises with the target's length (17.6 effective pairs for
two-letter words, 21.5 for nine-letter ones) while repetition falls with it, and the raw contrast between low- and
high-diversity pools (+0.034 on the manuscript) is mostly the instrument. Inside exact length classes it was −0.012.

**Toolkit.**
- `PoolSpec(metric='edge')` / `WIDTH_NEUTRAL_SELECTOR`: the same-line distance is the gap between the boxes plus one,
  so an adjacent word has distance 1 whatever the lengths; the distance preference stays (nearer words are the likelier
  sources), the width dependence goes. The viewer has it under Weights.
- `PoolSpec(target='cursor')` / `CURSOR_SELECTOR`: the source window is fixed before the word's width is known, the
  target being a provisional box one median word wide at its left edge. The review named this the selector a copying
  test needs. The viewer has it under Target.
- `stats.length_strata`, `three_contrasts`, `standard_contrasts`: every contrast is also formed inside exact word
  length (clipped to 2..9).

## 2. Pool size confounds the other way, so the length control alone hides the residual

**Trap.** Small pools (the top of a page or paragraph, the start of a line) are both low in diversity and poor in
repeats. A length-only control gave −0.009; with pool size added back the manuscript kept +0.026 (components) and
+0.035 (H2). The audit's first finding: a check that controls for length but drops the pool-size control that the
published result rests on, and scores one measure only, tests nothing.

**Toolkit.** `stats.standard_contrasts` always returns raw, inside length, and inside length × pool-size tertile, for
components, H2 and word diversity together; `format_contrasts` prints the whole table. Do not report one cell. The
contrast is pooled over bifolia (counts added) with bifolium-resampled intervals; cells under 20 tokens are dropped
and bifolia under 25.

## 3. Edge words have truncated windows whatever the text

**Trap.** The first and last word of a line and words beside drawings have small pools and low measured diversity in
every text; on all words the lines-above-only pool gave the manuscript −0.023, on interior words +0.028. The edge noise
was what earlier cuts read instead of the interior structure.

**Toolkit.** `stats.cohort_masks` / `interior_mask`: cohort A removes line-first and line-last words and pools under
15 words with the study selector; cohort B uses the lines-above pool. `standard_contrasts(..., line_words=...)` reports
every cohort.

## 4. A shuffle that keeps the recorded boxes puts words in boxes of the wrong size

**Trap.** Permuting words of any length inside paragraphs and leaving them in the slots' recorded rectangles put 41.6
percent of words in a box more than 1.5× too wide or too narrow (median error 38 percent). The selector weights by
distance and reads box geometry, so the control was distorted; "the association vanishes under a paragraph shuffle"
was withdrawn when the shuffle was re-typeset.

**Toolkit.** `shuffles.size_matched` / `words_in_units` exchange words only among words of the same character length
(every line keeps its character count; a recorded box still fits its new word); `words_any_length`, `words_in_lines`,
`reversed_lines`, `rotated_lines` and `lines_in_units` are re-typeset into the line frames (`typeset`, `typeset_fit`,
the latter fitting the letter size when a line lands in a slot of another length). `check_typesetting` is the guard
(box width off by 1.5× must stay below 1 percent); `vmsspatial shuffle-check` renders f75r and f33v for inspection.
`shuffled_in_boxes` (the old method) emits a DeprecationWarning.

**The same error with control texts.** A Markov or prose word dropped into the recorded rectangle of the manuscript word
it replaces is the same mistake, and it has been made repeatedly, by the Markov control of 29 October 2026 among
others. `controls.build_control` therefore typesets every control (`markov`, `prose`, `prose_native`, `stream`) into the
line frames by character position and runs `check_typesetting` on the result; the one-word-per-box kinds survive only
as `markov_box` and `prose_box`, which warn, carry a caveat in the bundle and are never a default.

## 5. A shuffle baseline must be scored in the observation's geometry

**Trap.** Comparing a statistic measured on the recorded rectangles with shuffles re-typeset into synthetic boxes gave
p-values that tested nothing (withdrawn). Likewise the copiers were quoted unsubtracted against the manuscript's excess
over its baseline: most of the copiers' high values sat in their own baselines.

**Toolkit.** `shuffles.baseline(ms, lines, geometry, geometry_kind, ...)`: recorded statistic → size-matched shuffles
with the recorded rectangles kept; synthetic statistic → re-typeset shuffles. Every bundle carries `geometry_kind`
(`make_bundle` warns when it is missing; `SpatialContext.describe()` prints it). `stats.baseline_summary` /
`shuffle_rank` report the excess over the shuffle mean, the rank and the one-sided permutation probability; compare
excesses between texts, each against its own baseline.

## 6. One realization is not a null

**Trap.** "Which words stand where contributes nothing" rested on one realization per rearrangement. Against 19
shuffles the manuscript exceeded every one; against 30, 29 of 30. Nineteen shuffles resolve nothing below p = 0.05,
thirty nothing below 0.032.

**Toolkit.** `shuffles.repeated` / `baseline` take `k`; `shuffle_rank` gives mean, range, rank, p and excess. Choose the
comparisons before looking at the values; say how many shuffles were run.

## 7. Recorded and synthetic rectangles are different instruments

**Trap.** The same Galen stretch gave +0.020 on the recorded rectangles and +0.134 on synthetic boxes proportional to
its own words' lengths; natural prose re-typeset shows a raw association that is the length effect once the geometry
carries the prose's lengths. A synthetic layout also inherits every frame rule (oversized boxes, drawing gaps, vertical
gaps, label slots, overflow placement), each of which was corrected after inspection of the control pages.

**Toolkit.** One implementation of the frames and placement (`geometry.py`), `bundle['geometry_kind']`, and the
control builders say which kind they produce (`controls.build_control` returns it). Report both when a claim depends on
it. The viewer shows any bundle, so a control layout can be inspected page by page.

## 8. Word diversity is not an order-free measure

**Trap.** `worddiv` (1 − Σ p²) with distance weights carries a weighting term (1 − 1/ESS); its raw contrast was large
(+0.098 interior) and the length-matched shuffles gave the same. It is the weakest and most geometry-dependent of the
three measures.

**Toolkit.** Documented in `measures.py`; `standard_contrasts` reports it beside components and H2, which carry the
results. Do not report word diversity alone.

## 9. Predictor and outcome can read the same words

**Trap.** The study selector pools the words beside the target, and word impact counts a twin anywhere in the 100-token
windows around it, the target's own line included; a line written from few forms gives both a monotonous view and a
repeat.

**Toolkit.** `outcomes.repeat_outside_pool`: a twin within 99 tokens outside the pool (optionally also off the target's
line); `PoolSpec(left=0)` / `LINES_ABOVE_ONLY` for pools of other lines only. Read these with the pool-size control
(a cone with no same-line part has small pools at the top of a page).

## 10. Direction is a property of the copier's configuration, not of copying

**Trap.** "The cone above should predict better than the cone below, so symmetry means no copying" is not a law:
copying has two channels (the target as a copy of what is above, and as the source of what comes below); the governed
words-in-view copier is nearly symmetric (+0.010), Timm's page draw is not (+0.068). A within-paragraph line shuffle
leaves a copier's association intact because the cones reach eight lines either way.

**Toolkit.** `PoolSpec.mirror()` and `stats.paired_contrast` (same tokens, one bifolium resampling for both). Run every
claimed control on the copier streams (`controls.STREAMS`) before saying what it would do to a copier.

## 11. Uniform weights must still be read at fixed pool size

**Trap.** The uniform-weight contrast was quoted as +0.011 (uncontrolled) when the fixed-pool-size value was +0.032.

**Toolkit.** `standard_contrasts` applies the same controls to any `PoolSpec`, `weight='uniform'` included.

## 12. Prose passages differ

**Trap.** A prose cut starting at a random offset depends on the order of calls in a script; one Rhazes stretch gave
+0.033 and another +0.012, and the text is passage-sensitive.

**Toolkit.** `controls.laid_in` and `fill_by_chars` take and return `start`; `build_control` records it; `make_bundle`
stores it under `passage`. Say which passage was scored.

## 13. Say which geometry and which policy produced a number

**Trap.** Numbers computed on different geometries (an older union of every rectangle a word touched against the
reviewed word-level boxes) or under different selector rules were compared as if one instrument had produced both; the
differences were of the size of the effects under discussion.

**Toolkit.** `load_bundle(policy)` makes the geometry explicit (`strict` or `sensitivity`), `SpatialContext.describe()`
reports the geometry kind, the policy and the provenance of the boxes, and `make_bundle` warns without a
`geometry_kind`. Put `describe()` in every report.

## 14. The copier comparison is not "as much copying as the models"

The hypothesis under test was less copying than the page copiers, which over-produce copies; a copier with a lower
copy rate shows a lower paragraph-level baseline and a smaller within-paragraph excess, which is the manuscript's
pattern. What these statistics establish is narrower than a copy rate; a dilution series of the copiers scored with
the same geometry-matched shuffles is the calibration they lack.

## 15. Detected positions are not recorded positions

The Rosettes foldout and f116v have no Voynichese rectangles. The toolkit finds word regions on the Beinecke image
and links them to the transcription without reading glyphs (docs/ROSETTES.md): ring words by a transcript-guided
segmentation of the unwrapped circle, labels by an order-preserving alignment under an ordering hypothesis. Every such
box carries `confidence` and the bundle marks the page in `detected_pages`; the geometry kind is `detected`, not
`recorded`. Circular text is also one line with other rings "above" it, so the pool selectors built for paragraph
text measure something else there. Use the extra pages for questions about those pages, report the confidence floor
you applied, and keep them out of the paragraph-text statistics.
Functions: `Manuscript.load(extra=...)`, `bundle.extend_bundle`, `rosettes.build`, `segment.strip_words`, `segment.best_assignment`.

## 16. Recorded rectangles carry the page's photographic warp

**Trap.** The rectangles were drawn on photographs of a bound book. A curvature shared across a page bows every line the
same way at the same horizontal position (docs/DEWARPING.md gives the method), and the camera adds a page-wide tilt and a little keystone. A line statistic
read off the recorded coordinates (a tilt, a sag, a step) mixes the scribe's hand with the photograph, and a page-level
pattern (a section whose lines all fall to the right) may be the scan as much as the writing.

**Toolkit.** `flatten.flatten(bundle, ms)` fits each page's shared warp from its own text lines (per-line intercept and
slope, one shared polynomial field, robust, leave-one-line-out) and returns a bundle with the warp removed,
`geometry_kind='flattened'`, the provenance extended and a per-page report (tilt, keystone, curvature amplitude and its
stronger side against the folio's gutter side). Say when a number comes from flattened geometry, and say what it
cannot separate: a page-wide slant written by the scribe goes with the camera's rotation, and a shared curvature is
only binding when its stronger side follows the gutter across pages. The box bottom is not the writing line either
(entry 17): say which baseline a number used, as well as which geometry. Functions: `flatten.flatten`,
`flatten.baseline_curves`, `flatten.page_table`, `baselines.word_baselines`, `SpatialContext.describe`.

## 17. The box bottom is not the baseline

**Trap.** A rectangle's vertical extent depends on the glyphs in the word: descenders (y, m, q, l, g) push the bottom
below the writing line by 0.08 to 0.13 H, gallows raise the top by 0.3 to 0.5 H, and a word written on a slope has an
axis-aligned box that reaches its bottom at the down-slope end. A line statistic read off the box bottoms carries a
per-word error of the size of the drift it measures, and words with and without descenders are not comparable.

**Toolkit.** `baselines.glyph_effects` measures the effects on the data at hand (a within-line regression on the Zattera
units, in page median box heights; the table is a result in itself), `baselines.word_baselines(..., 'glyph')` corrects
the bottom and the top for them and for the line's slope and combines the two with precision weights, and
`baselines.baseline_rms` says whether the correction helps (the manuscript's within-line residual goes from 0.169 to
0.129 H). `flatten` uses the glyph baseline by default. The boxes cannot give the ink's baseline or a box drawn off the
text's own angle; an ink-profile baseline from the page images is the next step for those.
Functions: `baselines.glyph_effects`, `baselines.word_baselines`, `baselines.baseline_rms`, `baselines.effects_table`.

## 18. Box edges are not ink edges

**Trap.** A recorded rectangle is a drawing around a word: it is padded on every side, it reaches the lowest
descender and the tallest gallows, and its vertical centre is not the writing. The box bottom is not the baseline
(entry 17), the box height is not the x-height (the median ink x-height is about half a box height), and a box
angle (least squares through box bottoms) is the drawing's angle, not the ink's. Reading a box edge as an ink edge
puts a per-word error of 0.1 to 0.3 H into any statistic that compares words with different glyphs.

**Toolkit.** `vmsspatial.ink` measures the ink itself on the Beinecke scans: per word the extent, angle, x-height
band (baseline and mean line), ascender top and descender bottom, with flags for every word where the ink could not
be read cleanly; `baselines.word_baselines(..., 'ink')` uses it and names its fallbacks; the records carry the
recorded box bottom so the comparison of box against ink is always available (`ink.unit_rows`). Use the flags:
a record flagged `band_not_found`, `paint`, `little_ink` or `registration_poor` is not a measurement.
Functions: `ink.load_ink`, `ink.unit_rows`, `ink.line_rows`, `ink.flag_names`, `baselines.word_baselines`.

## 19. Two photographs of one page do not share a warp: say which image frame a number used

**Trap.** The recorded frame is the Voynichese Project's photograph; the Beinecke scan is another photograph of the
same page from another camera position. A homography maps one onto the other to about a recorded pixel, and the
rest is a smooth warp difference that changes along and across the page (the per-line local shifts of the
registration measure it). A coordinate read on the scan and compared with a recorded coordinate without the mapping,
or an angle measured on the scan without removing the mapping's local rotation, mixes the two cameras.

**Toolkit.** Every number of `vmsspatial.ink` is returned in the recorded frame through the inverse of the page's
registration (`images.registration`, `images.Mapping.to_frame`, `images.region(...)['to_frame']`), angles through the
mapping's local rotation; the product records the source (`beinecke` or `display`), the registration's method,
residual, inlier count and per-line shifts, and a page whose registration failed carries no records. Report the
registration residual beside any ink number, and say `recorded frame` when quoting it. Functions:
`images.registration`, `images.registrations`, `images.Mapping`, `images.region`, `ink.summary`.

## 20. Never fit your own warp in a study

**Trap.** Every consumer used to refit the page warp (``flatten``) with whichever baseline it chose, so "flattened"
meant something different in every script, and a table flattened twice (once by the toolkit, once by the study)
or not at all looked the same as one flattened once. A writing-order effect measured in the recorded frame turned out
to be half page sag; a study then shifted ink values by hand to check it.

**Toolkit.** The warp is ONE shipped data product, `data/manuscript/page_warp.json.gz`, fitted once per page on the
baseline recorded in it (ink where the page has clean ink records, glyph otherwise). `load_bundle(policy,
warp='flat')` or `warp.flatten_bundle(app)` apply it to a bundle; `warp.transform(table, 'flat')` moves a baselines
table or the ink product with the same field; `warp.apply(folio, x, y, locus)` moves any y. `flatten.flatten` is the
fitter that builds the product (`warp.build`); a study calls it only to study the fit itself. Rotated, circular and
radial lines are not fitted and not moved: they keep their recorded positions in the flat state. Functions:
`warp.flatten_bundle`, `warp.transform`, `warp.apply`, `warp.build`, `docs/DATA_MODEL.md`.

## 21. Check the tags before combining two coordinate sets

**Trap.** Recorded boxes under two policies, flattened boxes, four baseline tables, ink values from another
photograph, detected boxes on the Rosettes image: nothing used to say which of them could be combined. A baseline
point from a flattened table beside a recorded box, or an ink baseline moved with a flattened bottom while the ink
stayed recorded, is wrong by exactly the warp.

**Toolkit.** Every coordinate-bearing table carries `frame`, `warp` and `source` (``vmsspatial.frames``);
`frames.require_same(a, b, what)` raises `FrameError` naming both tags and is called in every function that combines
two sets (`SpatialContext`, `line_frames`/`line_breaks`, `baselines.*`, `ink.baseline_points`/`intrusions`/`gap_table`,
`flatten`, `warp.transform`, `viewer_data.study_data`). Overlays drawn on the page image must be recorded / recorded
(`frames.require_recorded`): the image is the photograph, so flat coordinates cannot sit on it, and the atlas's Flat view
returns to recorded coordinates while the image is shown. The source may differ (the registration puts a Beinecke measurement into the recorded
frame to about a pixel plus the per-line residual); the frame and the warp state may not. Functions: `frames.tags`,
`frames.require_same`, `frames.require_recorded`, `frames.describe`.

## 22. A line statistic reads horizontal text

**Trap.** A line statistic (a tilt, a frame, a baseline fit) read off a rotated block or a ring measures nothing about
the writing line, and setting whole pages aside loses their horizontal lines with the others.

**Toolkit.** Every line carries an orientation record (``vmsspatial.orientation``: horizontal, rotated, circular,
radial, label, unknown, with the angle, the fitted circle and the cues) and the line statistics take
`orientations='horizontal'` by default, reporting what they skipped (`.skipped` on the result, `skipped` in a
report). `Manuscript.load()` holds every locus of every page with its type, so the other kinds can be studied
on purpose (`orientations='circular'`). `audit.flags.QUARANTINE` names the pages whose paragraph lines are not all
horizontal, `orientation.nonhorizontal_pages(load_bundle('sensitivity'))`; the line statistics skip lines, not pages.
Functions: `orientation.attach`, `orientation.line_mask`, `orientation.summary`, `orientation.nonhorizontal_pages`.

## 23. The toolkit's defaults are the public ones; a study names its own choices

**Trap.** The toolkit grew inside one research programme, and its defaults were that programme's shape: the
paragraph text of 207 pages, the Path 1 order, the recorded frame, the box-bottom baseline. A public toolkit with
those defaults would hand every new user our old mistakes as "the" manuscript.

**Toolkit.** `Manuscript.load()` is every page and locus by bifolium; `load_bundle()` is in the flat warp state;
baselines are `'auto'` (ink where clean, glyph otherwise); statistics read horizontal lines. A study passes its
choices explicitly, `Manuscript.load(pages='paragraph', order='path1')`, `load_bundle(policy, pages='paragraph',
order='path1', warp='recorded')`, `baseline='glyph'`, and says so in its Reproduce section; the tests pin the public
numbers and, separately, the same data under those arguments. Functions: `manuscript.STUDY`, `Manuscript.load`,
`load_bundle`, `bundle.manuscript_of`, `warp.page_status`.

## 24. A centred wheel composite is a display transform, not evidence

**Trap.** Translating every wheel of the circular pages to one common centre puts the rings of f57v, the zodiac
pages and the Rosettes on top of one another, and the eye reads the coincidence as a shared template or a common
instrument. The coincidence was imposed by the translation; radii, ring spacing and local deviations are what the
pages actually share or do not.

**Toolkit.** `wheels.centered_layout` changes nothing but a translation per wheel (no scaling, rotation, radius
normalisation or word rearrangement) and tags the result `frame='display'`: `frames.require_same` refuses to combine
it with measured geometry and `require_recorded` refuses to draw it on a page image. The measured quantities are in
the wheels product (`wheels.load_wheels`: centre, radius, ring fits, residuals, rejected loci with reasons) and in
the orientation records; compare radii and residuals there, with controls, before saying two wheels agree.
Functions: `wheels.centered_layout`, `wheels.load_wheels`, `wheels.fit_wheels`, `plot.plot_centered_wheels`.

## 25. Translation-only alignment scores describe resemblance, they do not test copying

**Trap.** Two page openings laid over each other by one translation and scored by shared area and wording look like
a copying test, and a high score in a ranked list of 19,701 pairs looks like a discovery. The score is symmetric (A on
B equals B on A), it has no direction, and it is high for many reasons that are not copying: a drawing of the same
shape, the same line-length habit, a ruled margin, the same section's vocabulary. The pairs were chosen by eye
before the controls were counted, and the counts of controls "at least as high" include the chosen pair.

**Toolkit.** `compare.measure` scores the first box too, whose overlap the alignment forces, reports the scored box counts beside every score,
and refuses selections in different frames or warp states; `compare.rank_pairs` returns a retrieval order with
competition ranks within the named pool and says so in its note; `compare.joint` withholds a bifolium value unless
every slot is complete. Read a score with its controls (the same cutoff, the same coordinate variant, intact blocks
of other pages), say which variant and anchor method produced it (`data['baseline']`, the selection's `frame` and
`warp`), and treat direction, template and copying as claims that need other evidence. Functions:
`compare.select`, `compare.measure`, `compare.details`, `compare.compare_sheets`, `compare.rank_pairs`,
`compare.first_line_scan`.

## 26. A located count proves nothing about an alignment

**Trap.** An order-preserving match of a page's words to the XML can put every word somewhere and still be wrong. The
XML lists a page in its own order: f49v's XML holds the column of letters before the paragraph, ZL reads letter, line,
letter, line, so one stream matched paragraph words to letters. Repeated words and one-letter words match anywhere, so a
greedy method can report a high count while it moves words between lines, and a page-level acceptance gate throws away
good words with the bad.

**Toolkit.** `vmsspatial.realign` aligns ZL in streams by locus category, then lets geometry decide what spelling cannot: a
placement must lie on its own line, read along the line's direction, in reading order, or beside its located neighbours.
It accepts word by word, keeps what is sound, and leaves a word without a box when it fails, with a reason
(`no_xml_word`, `transcriptions_differ`, `position_failed`). Judge an alignment by the boxes on the image, not by its
count: `plot.plot_page` draws them. Functions: `realign.realign_pages`, `realign.check_groups`, `audit.flags`.

## 27. A sheet is a label, not a stretch of the stream

**Trap.** In a sheet order a bifolium's words are one run of tokens, so a statistic can read a start and an end index.
In page order (`order='folio'`) its pages lie apart, and anything keyed by a global line or token index silently means
something else as soon as the order changes.

**Toolkit.** Sheet statistics gather words by label (`measures.group_table`), `Manuscript.bifolium_ranges` returns a
list of ranges, `mean_within` takes them, and `outcomes.token_meta` gives each token the stretch that holds it. Stored
products are keyed by page and locus or by token id (`ink.for_bundle`, `baselines.table_for`, `wheels.wheels_for`). Key
your own tables the same way. Functions: `Manuscript.bifolium_ranges`, `measures.mean_within`, `measures.group_table`.

## 28. A tilt put back by rotation leans the margin

**Trap.** Flattening moves words up and down only, so a flat page has lost its line tilt and kept every x. Turning that page
rigidly to bring the tilt back looks exact, and word sizes and distances hold, but a rotation also moves x, which flattening never did.
Each margin then leans by the page's own turn: drawn margin = true margin − turn, to 0.015 degrees on 183 pages. The added lean has a median of
1.10 degrees and reaches 4.75, f30v's 5.48 degree margin draws at 9.67, and between Path 1 neighbours the median gap in margin slope doubles from
0.95 to 1.86 degrees. A view built to compare angles would be drawing part of what it compares.

**Toolkit.** Undo a y-only change with a y-only change: `y + kx`, with `k = tan(recorded) - tan(flat)`. The Page stream's default does this, and
its rigid turn is labelled as leaning the margins. To read a margin, use recorded coordinates or the unturned points (`x`, `y` in its export,
not `drawn_x`, `drawn_y`). Functions: `viewer/js/stream_math.js` `orient`, `compare.page_drift`.

