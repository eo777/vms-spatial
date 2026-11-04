# f1r and f8r: independent MSI margin check

Audit completed 2026-11-03, before removing the unsuccessful faint-writing inspection images. The compact measurements are preserved in `data/manuscript/msi_leaf_audit.json.gz`. This product supplements the canonical leaves data; it has not replaced it.

## Result

The existing **recorded text registration is consistent** with independently matched features in the MSI photographs. Both the MSI and reference photographs show curved pages: neither is flat-page ground truth. In photographic projection, the current bottom margin is about 3 mm larger than the MSI measurement on both pages. F8r's top and inner margins are about 3 mm smaller. These differences can include page curvature and how the leaf was held, as well as edge selection and scale.

All dimensions below are approximate projected millimetres. They are the visible parchment around the complete located text envelope, including tall opening glyphs but excluding the plant illustration and unboxed folio number. A concealed strip in the binding is not measured.

| Measurement | f1r existing | f1r MSI | f8r existing | f8r MSI |
|---|---:|---:|---:|---:|
| Visible width | 152.3 | 154.0 | 149.5 | 158.0 |
| Height at text-centre x | 224.2 | 222.6 | 225.0 | 225.9 |
| Top text margin | 15.6 | 14.9 | 57.9 | 60.9 |
| Bottom text margin | 38.9 | 35.9 | 41.6 | 38.3 |
| Inner text margin | 11.2 | 10.7 | 12.5 | 15.4 |
| Outer text margin | 21.5 | 22.1 | 22.9 | 23.1 |

The two frames have different tilt and perspective, so these envelope margins are not exact distances to every individual glyph. Sampled edge curves, the MSI-space text envelope, and transformation matrices are retained for more specific measurements. Decimal precision should not be confused with physical accuracy: page curvature, different flattening, irregular edges and the concealed gutter limit interpretation.

The external ruler calibrates the image plane; it does not measure distance along the curved parchment. A global homography can reconcile camera perspective but cannot flatten a nonplanar leaf. Recovering physical surface distances would require independently constrained page shape or a validated local dewarping model. The margin discrepancy alone is not sufficient evidence to change a physical copy placement.

## Independent calibration and alignment checks

The MSI ruler gives **28.9081 px/mm for f1r**, fitted to 107 one-mm marks. F8r gives **29.0347 px/mm** from 48 marks on its upper ruler and **29.0359 px/mm** on its lower ruler. The 740 dpi TIFF tag corresponds to 29.1339 px/mm; the photographed rulers were used instead. The orthogonal axis assumes square pixels and a near-parallel imaging plane, rather than providing a separate two-dimensional calibration.

The existing toolkit uses a common Yale-scan scale of 15.84 px/mm, based on the catalogue's 225 mm median leaf height. Its “measured” scale is not an independent physical measurement of every leaf. The two sides of f1 and f8 previously differed by approximately 6–7 mm in apparent height; that discrepancy cannot represent a real difference in the height of the same physical leaf.

For the text check, SIFT correspondences were matched directly between the original Voynichese display image and the MSI photograph. Correspondences inside recorded text boxes were compared with predictions from the existing display/Beinecke registration, saved per-line shifts, and the separately fitted Yale-to-MSI homography:

| Page | Matched text features | Median disagreement | 95th percentile disagreement |
|---|---:|---:|---:|
| f1r | 1,343 | 0.073 mm | 0.162 mm |
| f8r | 790 | 0.215 mm | 0.430 mm |

These are matched-feature residuals, not confidence intervals or a check of every box boundary. They support the text registration. They do not validate the learned page warp, which intentionally moves flat coordinates away from the photographed text.

### Recorded boxes versus dewarped coordinates

The cyan boxes and the alignment check use **recorded, as-drawn geometry**, with the existing per-line image-registration shifts. They do not use the flat/dewarped coordinates. Flat coordinates intentionally remove shared curvature and tilt and therefore should not be overlaid directly on an unflattened photograph.

The existing `page_warp.json.gz` model was checked separately; it was not refitted from MSI:

| Page | Ink-baseline lines / points | Shared curvature amplitude | Stronger-curvature side | Expected gutter |
|---|---:|---:|---|---|
| f1r | 25 / 198 | 0.134 word heights | Left | Left |
| f8r | 18 / 138 | 0.291 word heights | Right | Left |

Amplitude is the peak-to-peak nonlinear field across the text block at mid-height, excluding overall tilt. F1r's weak curvature is compatible with gutter-side distortion, but does not establish its physical cause. F8r's stronger side is opposite the gutter. Neither is an independent MSI detection of binding distortion. The product's `gutter_side` field is misleadingly named: it reports the stronger-curvature side. The correction changes vertical word positions only; it cannot recover horizontal compression, a physical surface, or hidden parchment at the fold. See [DEWARPING.md](DEWARPING.md) for the method and limits.

## What the margin discrepancy means

In the MSI comparison figures, green follows the sampled visible leaf edge, orange is the saved Yale edge projected through the text registration, and cyan shows the toolkit's word boxes. The orange bottom lines extend below the visible MSI leaf. Inspection of the Yale scans also shows that the strongest lower boundary can belong to the underlying stack or backing rather than the front leaf. A single straight line misses the curled and irregular lower edge.

The mismatch also includes camera and flattening differences. At f8r's text centre, the independently calibrated mapping gives approximately **6.149 recorded px/mm horizontally and 6.323 vertically**, versus the current scalar 6.412. A one-number replacement would correct one direction while distorting the other. The stored projective mapping and sampled edge curves preserve this distinction.

For that reason, the audit did **not** silently replace canonical `leaves.json.gz`, registrations, the page warp, or copy-chain placements. The correct integration is to support the measured per-page transformation and visible edge curves in the parchment-coordinate view, with the current scalar form retained as an explicitly approximate fallback. Refit or review edge detection against the front leaf rather than the strongest page-stack boundary. Verify both sides of a physical leaf before enforcing shared dimensions; there are no independent MSI verso captures in this audit. Any downstream source-window or weight rebuild should follow that geometry change, not a similarity-driven adjustment of the copy offsets.

## Reproduction and retention

`scripts/audit_msi_leaves.py` reads the two original 450 nm TIFFs, the existing image cache, and the frozen Yale-to-MSI transforms in the viewer's `references.json`. Set `VMS_SPATIAL_IMAGES` to the real cache path if a sandbox redirects LocalAppData. Original filenames, Drive IDs, hashes, sampled ruler marks, edge coordinates, pre-audit toolkit records, measured dimensions, transform matrices, and the existing warp summary are in the compact product. The original faint-writing pilot's code and small provenance files remain under `research/bifolium_drift_20261030/msi_pilot`; its large TIFFs and enhancement images can be removed without losing the geometry results. No full model run is required to read the audit.

The annotated figures and readable summary replace the old inspection viewer at:
`/chain_search/copy_windows/lexical_pilot/spatial_weights/msi_pilot/index.html` on the research server.

MSI credit: **The Lazarus Project and The Chester F. Carlson Center for Imaging Science at Rochester Institute of Technology**. Manuscript: **Beinecke Rare Book & Manuscript Library MS 408**, f1r and f8r. Visible reference scans: Yale University. [Public release](https://manuscriptroadtrip.wordpress.com/2024/09/08/multispectral-imaging-and-the-voynich-manuscript/).
