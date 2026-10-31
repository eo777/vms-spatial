# Independent verse pages

Use `vmsspatial.verse_layout` when a control must retain one source line per physical row without borrowing Voynich page frames. This is distinct from `poetry.typeset_verses(..., mode='native')`, which retains source breaks as inputs but wraps into manuscript frames.

```python
from vmsspatial.verse_layout import VerseLayout, typeset_independent
bundle = typeset_independent(verses, VerseLayout(
    lines_per_page=48, char_width=8, word_height=14, line_pitch=20,
    word_gap=1, left_jitter=1.5, gap_jitter=.25,
    line_jitter=.05, line_scale_jitter=.05, seed=20261030))
```

```sh
python -m vmsspatial.verse_layout verses.json --out control.json.gz --lines-per-page 48 --left-jitter 1.5 --gap-jitter .25
```

No manuscript data is loaded by the placement function. `words`, `lines`, `geometry`, components, page dimensions, source IDs and the complete configuration are returned in a standard schema-2 spatial bundle. `SpatialContext` can score it. The manuscript atlas's built-in folio layout does not automatically know these invented pages; use `page_layout` for independent page previews. The line `bifolium` field groups each synthetic page only and does not assert historical binding.

Every source record needs `book`, `line`, and `words`. Optional `indent_chars` and `space_before_lines` supply actual indentation and stanza gaps. If actual page breaks are known, supply `source_page` on every record; otherwise pages contain at most `lines_per_page` source records. Books always start new pages. Records within a book and supplied source page must be contiguous. Source numbering is retained, not interpreted as canonical metrical numbering.

Word width is character count times the line's character advance. Lines are left aligned and ragged right; they never wrap or stretch to justify. Automatic page width encloses the longest line. A fixed `page_width_chars` fails if a line does not fit. The page canvas may change when word or line lengths change; it is not used to shrink the words.

Dispersion controls are explicit bounded uniform perturbations: `left_jitter` is +/- character advances at each line start; `gap_jitter` is a relative perturbation of each interword gap; `line_jitter` is +/- fractions of line pitch at each row; `line_scale_jitter` changes the character advance of a whole line. Every amplitude defaults to zero. Unsafe settings that could reverse word order or overlap rows fail validation. `word_gap`, `line_pitch`, margins, character width, box height, pagination and seed are separate controls. These are synthetic typography assumptions, not measurements of historical handwriting.

Random geometry depends on slots and the seed, never the word spelling. Exact-character-length permutations keep every box identical when replayed with the same configuration. Test this replay before caching geometry. Preserve one-character word positions when excluding their undefined adjacent-letter-pair distributions from pair statistics.

For a layout-sensitivity study, hold the text, source line boundaries, page assignment, scoring rules and permutation draws fixed across dispersion settings. Uniformly enlarging a page cancels out when distances are normalized by median word advance and line pitch; it is not a substantive dispersion test. Geometry, source windows and page boundaries must still match each observation's null. These controls preserve the supplied transcription's lineation; without measured indentation, stanza boundaries and pagination they are not facsimile reconstructions.
