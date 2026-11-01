# The Word search page

`viewer/search.html` lights up the words that match a pattern on every bifolium at once. Each bifolium is a small tile of its pages,
up to six patterns run in their own colours, the sheets go in any order, and a page opens to show its matches on its image. It searches
spellings and draws positions: it is not a statistical test. The language and the tiles are in `viewer/js/pattern_math.js`, tested in
`viewer/test/pattern_math.test.js`.

## Patterns

The language is the Echo rule builder's. A term is a glob over the whole spelling, and no regular expression is ever run.

| Write | Meaning | Example |
|---|---|---|
| `*` | any letters, or none | `*aiin` |
| `?` | one character | `ch?y` |
| `AND` `&` | both | `qok* AND *y` |
| `OR` `\|` | either | `chol OR chor` |
| `NOT` `!` | not; binds before AND, AND before OR | `*y AND NOT qo*` |
| `( )` | group | `(chol OR chor) AND 1:*y` |
| `-1:` `1:` `-2:` … | the word before or after a match, within its line | `*aiin AND -1:*k*` |
| `[li]` `[lf]` | the word starts or ends its line | `[li]p*` |
| `[pi]` | on a paragraph-initial line | `[pi]p*` |
| `[pgi]` | on a page-initial line, a page's first prose line | `[pgi]p*` |
| `[lpi]` | on a later paragraph-initial line | `[lpi]p*` |
| `[npi]` | on a line that is not paragraph initial | `[npi]p*` |
| `[!code]` | that place negated, the spelling still applies | `[!pgi]p*` |

`NOT` before a term negates all of it, spelling included: `![pgi]p*` is every word except the page-initial p-words, and `[!pgi]p*` is the
p-words off a page's first line. Operator words are capitals only, because lowercase `or` is a Voynich word. Qualifiers stack, and an offset
comes first: `-1:[li]*`. Under each box the page writes out the grouping and names what stops a pattern from being read, and a pattern
that cannot be read shows no results.

A term matches the whole spelling, so `aiin` finds only that word and `*aiin*` finds every word containing it. On voynichese.com a plain
term matches inside a word and `^`, `$` anchor it, so the page says what to write when it meets those. Merge q matches every word and
neighbour without one initial q, and a term starting q then finds nothing.

## Controls

| Control | Address | What it does |
|---|---|---|
| A pattern box; Add pattern | `q1` … `q6` | the key names the colour, so a pattern keeps its colour when another is removed |
| Merge q | `merge=1` | as above |
| Group; Group by, under Settings | `group`, `by` = section | the whole manuscript, a Golf group or a section. Counts follow the selection |
| Order | `order` = path1 (bifolia is the default) | Manuscript by bifolium, or Path 1, a proposed glyph-statistical ordering and not an established chronology |
| Drag a tile's heading; Alt + ← → on its grip | `custom`, the full list of bifolia | moves the sheet. Reset order returns to the chosen order. A custom order applies only to the same set of sheets |
| Saved order | none | the boundary sets saved on the Page stream in this browser, read only |
| Columns | `columns` = faces (singulion is the default) | singulion Ar Av Br Bv, or the physical faces Bv Ar and Av Br |
| Tile size | `size` = 100, 140, 200, 300, 450 (70 is the default) | the height of a page in pixels |
| Open in Page stream | none | the same group and order on that page. `group`, `by`, `order`, `columns`, `custom` and `pages` mean the same on both pages, so a link's tail works on either |
| Click a page | `open`, `image=0`, `labels=1` | the page on its image, with the transcription beside it. The wheel zooms, dragging pans, ← → step through the sequence |
| Counts by bifolium | none | counts and rates per 1,000 words, sheet by sheet, in the order shown |
| Download matches CSV, under Settings | none | one row a match: pattern, folio, bifolium, locus, place on the line, word, whether it has a box |

## Reading it carefully

- **A count is of words.** A box that holds several words lights up when any of them matches, and the count stays a count of words.
  271 words have no box, so a count can run past the marks on a tile: each pattern's line says how many of its matches that is.
- **A share is over the words where the pattern can match.** `[pi]p*` is out of the words on paragraph-initial lines. Spellings and neighbours
  never narrow that base. No share is given over fewer than 20 words.
- **Patterns overlap.** A word matching two patterns counts under both and is drawn split between their colours.
- **Unreadable tokens stop neighbours.** A token with `?` never matches, and no neighbour term reaches across one or across a line end. The
  bundle drops those tokens, so this page reads them from the alignment review file and puts them back as gaps (`textLines`). The same file must
  load for `-1:` to be exact, and the page says so if it does not.
- **`first` means a paragraph here.** The compact pages also set it on every label, circle and radial line. `textLines` counts it on paragraph lines
  only, which gives 740 paragraph-initial lines, 207 of them page initial.
- **Tiles are in recorded coordinates**, at one scale, so words sit where they sit on the photograph. No measure is read from a tile.
- **Page images** are the Voynichese display images, drawn with that image's own word rectangles, as on the Atlas. A box with no rectangle on the
  image is left out and the page says how many. f116v has no image, and fRos uses the toolkit's copy with its detected boxes.

## Origin

The language is ported from `workbench_core.js` of the Echo rule builder. Run on each one's own copy of the text, the two return the same words at
the same places, with the same rate bases and error messages. The reference counts in the tests come from that engine.
