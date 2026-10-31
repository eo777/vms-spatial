# Registered image overlays for articles

`vmsspatial.illustrations` exports a compact manuscript crop with the exact boxes
supplied by an analysis. It writes a JPEG, a JSON record of crop-space polygons,
and a self-contained SVG with the image and outlines. It uses the existing image
cache and registration, including local shifts for each manuscript line.

```python
from vmsspatial.illustrations import export_overlay

# records is a list selected by YOUR analysis, not by the illustration exporter.
# Each entry has id, label, box=[x0,y0,x1,y1], line (the ZL locus of the word's line on
# the page), and role (target/source/candidate/context).
export_overlay('outputs/example', folio, records, warp='recorded', labels=True, max_width=1800)
```

Or save `{ "folio": "f75r", "warp": "recorded", "words": [...] }` and run:

```sh
python -m vmsspatial.illustrations example.json --out outputs/example --labels
```

Install the `images` extra. `source='beinecke'` uses the registered Yale scan;
`source='display'` uses the Voynichese display image. An existing cache is reused;
first use can download an image or calculate registration. `image_overlay(...)`
returns `(PIL.Image, metadata)` for custom plots without writing anything.
`overlay_svg(image, metadata)` supplies the portable SVG rendering.

The JSON includes the folio, image credit/source URL, registration quality,
original boxes, crop origin, resize scale and mapped polygons. It can drive a
native JavaScript overlay, including a heatmap from per-word values supplied in
the records. The toolkit's atlas remains the full-page interactive viewer; this
exporter supplies small article assets without copying that application.

Important boundaries:

- The image is a photograph, so only recorded coordinates sit on it. `load_bundle` gives
  flat coordinates by default, so every call must state `warp='recorded'`. A call that
  leaves it out, or passes `warp='flat'`, raises `FrameError`. Take the boxes from
  `load_bundle(..., warp='recorded')` or `warp.transform(bundle, 'recorded')`.
- Pass the actual geometry and eligibility from the calculation you illustrate.
  The exporter does not select source pools or assume a triangular window.
- Registration changes display coordinates only. It does not correct or replace
  the analysis geometry, or validate transcription assignments.
- Name the line by its ZL locus on the page (`bundle['lines'][l]['locus']`), the key of the local shifts.
  The exporter rejects a missing local-line mapping when a page has local shifts.
- Preserve image and coordinate credits when publishing. The exporter records
  the image source; the caller must also carry the analysis's coordinate and
  transcription provenance and applicable licenses.
- Output filenames are explicit and overwritten on rerun. Do not use them for
  unique source files. Full scans stay in the existing cache outside the toolkit.

The continuous-similarity article illustrates a Gaussian integrated over two
unit-mass rectangles. That study-specific weighting and its source selection
remain outside this general-purpose overlay exporter.
