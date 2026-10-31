# Word positions on the Rosettes foldout and the circular pages

The Voynichese Project recorded word rectangles for 225 pages. Two pages have none: the Rosettes foldout
(ZL page `fRos`, the nine-rosette face of f85/f86: 160 loci, 540 tokens) and f116v (two Voynichese tokens on the
last page). Twenty further pages have rectangles but were outside the study's token set, which holds paragraph
text on the 50 Path 1 bifolia: the circular and astronomical pages f57v, f65r, f67v1, f68r3, f68v1, f69v, f70r1,
f70v1, f70v2, f71r–f73v (zodiac) and f116v. The toolkit now reaches all of them.

## What `extra=True` adds

`Manuscript.load(extra=True)` appends the 20 pages and the Rosettes' labels and circular texts (its eleven floating
paragraphs were study text already). Lines come from the same lattice reading as the study tokens (uncertain-reading
tokens omitted); each page joins the node of its bifolium, or a new node at the end of the order (group `—`) for the
zodiac bifolia K:71-72 and L:73-74, and every other page's non-paragraph loci (labels, circular and radial text),
which the Voynichese Project recorded: all 227 pages and all loci, each line with its ZL locus type and an
orientation record (`extra='all'` is the older spelling of the same thing).

`load_bundle(policy, extra=True)` re-sequences the bundle in that order. New lines take the alignment review's
boxes (strict or sensitivity assignments by policy); the Rosettes take the detected boxes described below. The bundle
records `extra_pages`, `extra_lines`, `detected_pages` and `detected_confidence`; the study bundle itself is unchanged
(34,977 tokens, 207 pages).

Scores on circular text are not comparable with scores on paragraph text: a ring is one line, the words "above" it are
other rings, and label pools are small. Keep the extra pages out of a statistic unless the question is about them.

## How the Rosettes positions were found

The goal was never to read glyphs. The transcription already says which words stand where: locus types (`Cc`
circular clockwise, `Ca` anticlockwise, `L0` label, `Pb` floating paragraph), the transcriber's comments
(`<!c:k>` Petersen's circle and label number, `<!HH:MM>` the clock position where a circular text starts,
`<!Spiral>`, `<!I>`–`<!VIII>` groups, `<!left of clock>`), and the ZL header's circle numbering (columns 1 4 7 / 2 5 8 /
3 6 9). The image is the Beinecke's IIIF scan of the 85v/86r foldout (7925 × 7268 px, image 1006231). The method,
in `vmsspatial.segment` and `vmsspatial.rosettes`:

1. **Rings.** Each rosette's centre is refined on the ink mask (the radial profile is sharpest at the true centre) and
   its text band `[r0, r1]` recorded in `resources/rosettes_layout.json` (chosen from the radial ink profile and the
   detector candidates, checked on the unwrapped strips). The band is unwrapped into a straight strip from the
   start angle in the reading direction, the column ink profile is cut at the gaps, and the cuts are matched to the
   transcribed words by their glyph counts: a word's width is close to proportional to its number of Zattera units,
   so the N-word segmentation whose widths fit the N glyph counts best is chosen (`fit_widths`, a dynamic programme
   that merges runs a gap inside a word separated and splits runs the gaps did not separate). Segments return to
   image coordinates through the polar map as axis-aligned boxes. A spiral is unwrapped with a radius that changes
   with the angle; both windings are tried. Two rings offering the same pair of rosettes (`8|9`) are resolved jointly
   by ink length against glyph count.
2. **Labels and paragraphs.** Candidate word rectangles come from the CRAFT character-region detector (EasyOCR, the
   recognizer off) run in tiles over the whole image, deduplicated, and filtered to text-like sizes; ring words are
   removed. Each rosette's territory (nearest centre) holds its Petersen labels. A run of loci joined by the `+`
   locator (consecutive lines of one label column) is matched as a block to the cluster of stacked candidates that
   fits it best in reading order. The remaining labels are aligned in Petersen order to the candidates under several
   ordering hypotheses (clockwise or anticlockwise from each quarter, with adjacent candidates kept together in
   reading order; or plain reading order) by an order-preserving alignment scored on width against glyph count; the
   cheapest hypothesis wins. Labels beside the small "clock" circle take the nearest candidate on their side. The
   roman-numeral groups have no placement hint and are matched to left-over candidates with a confidence capped at
   0.3.
3. **Confidence.** Every token carries a `confidence` in [0, 1] and a `method` (`ring`, `spiral`, `label-block`,
   `label`, `clock-label`, `roman-group`). Ring confidence is 1/(1 + fit error) discounted when the run count misses
   the word count; label confidence is the matched share discounted by the mean width error. Boxes below the floor
   (`confidence_floor` 0.25) are kept in the supplement but excluded from the bundle.

Result (`data/manuscript/supplement_fRos.json`): 540 tokens, 472 boxed, 449 at or above the floor; the 12 circular
texts (355 tokens) fit with errors of 0.6–1.1 glyph widths. The ring positions are reliable to about a word; the
label assignments are the alignment's best guess under an ordering hypothesis and must be read as such. The viewer's
page overlay (Page image on fRos) shows every box on the Beinecke image for review; `scripts/rosettes_geometry.py
--overlay` writes the same picture to a file.

## Reproducing

    vmsspatial fetch-data --group images          # the Beinecke scan (12.7 MB) by its IIIF URL
    pip install easyocr                           # CRAFT detector; CPU is enough (about five minutes in tiles)
    python scripts/rosettes_geometry.py --image data/images/beinecke/fRos_1006231.jpg \
        --candidates data/manuscript/fRos_candidates.json --overlay review.jpg --display viewer/img/fRos.jpg

The candidate cache is shipped, so the pipeline runs without the detector installed. Editing a band or a centre in
`rosettes_layout.json` and re-running is the intended way to correct a ring; a wrong label is corrected by editing its
token record in the supplement, which the bundle and the viewer read as it stands.

## Other tools considered

Kraken (baseline segmentation for manuscripts, line level, curved baselines; poor Windows support), docTR (DBNet word
boxes, rotated with `assume_straight_pages=False`), Transkribus/eScriptorium (layout analysis with training), and
plain connected components with directional dilation. CRAFT was chosen because it links characters into words along
any orientation without training, which the radial and circular text needs; the transcript-guided ring segmentation
replaces the detector where the text runs on a known curve, and connected components (`segment.ink_components`) are
the fallback when no detector is installed.
