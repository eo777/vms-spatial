# Poetry controls

`python -m vmsspatial.poetry verses.json --out control.json.gz` uses the toolkit's existing `controls.native_layout` with `start=0` and sensitivity-policy line frames. Words use each frame's default character width. Native source lines are retained as inputs; a source line that exceeds its frame follows the toolkit's normal carry-over rule. The audit reports how many source lines split across physical rows. The command never repeats a short text to fill unused slots, and repeats geometry templates only when a long text needs another batch.

`--mode reflow` intentionally removes source lineation. The finite word stream is filled to the recorded character budgets and passed to `geometry.synthetic_geometry`. This is a sensitivity comparison, not the native poetry control.

Input is a JSON list of `{ "book": "1", "line": 1, "words": ["arma", "virumque", "cano"] }` records. `book` prevents accidental treatment of book boundaries as adjacent text in downstream analysis. `line` is a source record identifier. The bundle retains a source-verse ID for every token and has `geometry_kind='synthetic'`, letter components, template-page locators and the layout audit. Empty input and malformed tokens fail rather than silently changing the corpus.

Import the named sources with `python -m vmsspatial.poetry_sources aeneid --source-dir /path/to/local/html --out aeneid.json`, or use `towneley_creation`. The importer writes a provenance sidecar with source hashes. Aeneid inputs are named `aeneid-01.html` through `aeneid-12.html`; Creation accepts `towneley.html` or a numbered text extraction named `towneley-creation-web-extract.txt`. Inputs must be obtained explicitly; this command does not download them.

## The controls named by Timm (2016)

- **Towneley Plays: The Creation**, Middle English, England and Pollard's 1897 edition. Timm cites `http://name.umdl.umich.edu/Towneley`. A UVA/OTA transcription is mirrored at `https://blocksclass.com/libr/TownleyPlays.htm`. Extract the 267 numbered lines of *The Creatio*, not the entire play collection; exclude speaker labels and stage directions. The electronic-source header restricts commercial use, so this extension does not redistribute its text under the toolkit's MIT license.
- **Virgil's Aeneid**, Latin, all twelve books. Timm cites `https://sacred-texts.com/cla/virgil/aen/index.htm`; an archival mirror is `https://spiritmaji.com/sacredtext/cla/virgil/aen/aenl01.htm` through `aenl12.htm`. Use the Latin pages, not the neighboring English translation. The archived HTML has editorial omissions, transpositions and a paragraph split within a metrical line; source HTML lines should not be described as a canonical metrical edition without a separate reconstruction.

The Quran is another control in the paper, but should be identified separately rather than silently labeled another poetry corpus.

## Safe comparison rules

Use source records before typesetting for a native ordinal comparison, and the bundle's physical rows for a typeset comparison. Whole-page overflow that the older line-array API appends to its final slot is separated into physical rows here. The source stream must reproduce exactly; missing geometry is reported.

Synthetic observations require the same typesetting for shuffles. Exact character-length permutations leave every input line's length pattern unchanged, including the carry decisions. Check a shuffled replay against the observed geometry before caching boxes. Do not drop arbitrary-length words into the original manuscript's rectangles.

For natural-language words, use letters rather than the manuscript's Zattera components. A pairwise JS distance can be calculated from each word's normalized adjacent-letter-pair counts. A one-letter word has no such distribution: keep its position in the line and exclude the undefined pair from the statistic. For a common-pair comparison, apply that same eligibility mask to identity and edit distance. `1 - sqrt(JSD_base2)` is similarity; `sqrt(JSD_base2)` is distance. Neither is the source-pool H2 statistic.

Timm's poetry tables use nine preceding lines, horizontal offsets -5 through +5, and -5 through -1 on the current line. Identity and **exactly one** ordinary Levenshtein edit are distinct metrics. The manuscript-specific similar-glyph substitution groups must not be applied to English or Latin. Normalization, denominators and source scope need explicit recording: these choices can prevent an exact numerical replication of published percentages.

The current control study normalizes to lowercase alphabetic tokens, expands `&` to `and`, retains supplied letters inside editorial brackets, and splits hyphenated forms. Its native HTML-line reconstruction is an updated comparison, not a verified reproduction of Timm's original numeric tables.
