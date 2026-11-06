"""Page images and their registration to the recorded word rectangles.

Two images exist of every page with recorded rectangles. The Voynichese Project's display image (636 x 900 px, the
frame the rectangles were drawn in, scaled) is too coarse for ink work (x-height about 10 px). The Beinecke Rare
Book and Manuscript Library's scans, served by Yale University Library's IIIF service (about 2,800 x 3,750 px per
page), are another photograph of the same page: a different camera position, so a different warp. This module

* indexes the Yale manifest once (``build_beinecke_index`` -> ``resources/beinecke_iiif.json``: canvas label, image
  id, size) and maps the toolkit's folio names to canvases (``beinecke_index``; a foldout folio may have several
  candidate canvases, resolved by the registration);
* caches the images OUTSIDE the toolkit and the research workspace: ``%LOCALAPPDATA%/vmsspatial/images`` (or
  ``~/.cache/vmsspatial/images``), overridable with the environment variable ``VMS_SPATIAL_IMAGES``; downloads are
  sequential with a pause, resumed on rerun, and a file whose size matches is never fetched again
  (``page_image``, ``fetch_images``, ``vmsspatial fetch-images``);
* registers the recorded frame to each image (``registration``): for 'display' a least-squares affine from the
  review's native rectangles (exact up to rounding); for 'beinecke' SIFT + RANSAC between the display image and the
  scan at one third scale (homography; similarity when inliers are few), composed with the display affine, plus a
  LOCAL shift per text line taken from the inlier residuals around that line (the two photographs' warp difference;
  a smooth quadratic field of the residuals stands in for lines with few inliers). Registrations are a shipped
  data product, ``data/manuscript/registrations.json.gz`` (numbers only: per page and source the matrix, the
  residual field, the per-line shifts and the quality; ``build_registration_product`` writes it from the cache,
  ``registration`` reads it first and recomputes only with ``force`` or for a page the product lacks, caching the
  result in ``<cache>/registration_<source>.json``). A page whose registration fails is flagged, never measured;
* reads a region of a page image around a mapped rectangle in memory, with the inverse mapping back to the recorded
  frame (``region``). Nothing here writes an image crop.

Images: Beinecke Rare Book and Manuscript Library, Yale University (MS 408), via Yale University Library's digital
collections; the Voynichese Project's display images are loaded from voynichese.com. The repository stores neither.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import paths

MANIFEST_URL = 'https://collections.library.yale.edu/manifests/2002046'
IIIF_BASE = 'https://collections.library.yale.edu/iiif/2/%s'
INDEX_FILE = 'beinecke_iiif.json'
SOURCES = ('beinecke', 'display')
CACHE_ENV = 'VMS_SPATIAL_IMAGES'
USER_AGENT = 'vms-spatial/0.1 (research toolkit, https://github.com/eo777/vms-spatial)'
PAUSE_S = 1.0                      # between requests
RETRIES = 3
REGISTRATION_VERSION = 4
PRODUCT_KEY = 'manuscript/registrations.json.gz'
PRODUCT_VERSION = '2026.10.30.1'
PRODUCT_FIELDS = ('folio', 'source', 'version', 'ok', 'method', 'matrix', 'residual_px', 'n_inliers', 'n_matches', 'scale', 'rotation_deg', 'image_id', 'image_size',
                  'candidates', 'display', 'lines', 'field', 'field_frame', 'shift_range_px', 'shift_median_px', 'field_amplitude_px', 'flags', 'computed')
SCAN_FACTOR = 3                    # the scan is matched at one third of its size
RANSAC_PX = 4.0                    # reprojection threshold at that scale (about 1.3 recorded-frame px)
MIN_INLIERS_HOMOGRAPHY = 60
MIN_INLIERS_SIMILARITY = 15
LARGE_RESIDUAL_PX = 3.0            # a page's median reprojection error above this (recorded px) flags its registration as poor
FEW_INLIERS = 200
DISPLAY_TRIM_PX = 3.0              # display-px residual beyond which a group's display parts are left out of the affine
DISPLAY_MAX_RESIDUAL_PX = 4.0      # the display rectangles are rounded integers (about 1.2 px of residual); a frame built from two XML parts gives hundreds
LINE_MIN_INLIERS = 8               # a line takes the median residual of its own inliers when it has this many
FOLIO_RE = re.compile(r'^f(\d+)([rv])(\d*)$')
MENTION_RE = re.compile(r'(?<!\d)(\d+)([rv])(?![\d])')
CREDIT = 'Beinecke Rare Book and Manuscript Library, Yale University; Yale University Library digital collections (IIIF)'


# ----------------------------------------------------------------------------- cache
def cache_dir() -> Path:
    env = os.environ.get(CACHE_ENV)
    if env:
        return Path(env).expanduser()
    local = os.environ.get('LOCALAPPDATA')
    base = Path(local) if local else Path.home() / '.cache'
    return base / 'vmsspatial' / 'images'


def _cache_index_path(source: str) -> Path:
    return cache_dir() / source / 'files.json'


def _read_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _write_json(obj, path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True), encoding='utf-8')
    os.replace(tmp, path)


def cache_summary() -> dict:
    """Files and bytes in the cache per source."""
    out = dict(dir=str(cache_dir()), sources={})
    for s in SOURCES:
        d = cache_dir() / s
        files = [p for p in d.glob('*.jpg')] if d.is_dir() else []
        out['sources'][s] = dict(files=len(files), bytes=sum(p.stat().st_size for p in files))
    return out


# ----------------------------------------------------------------------------- the Yale index
def _canvas_rows(manifest: dict) -> List[dict]:
    """[{label, id, width, height}] from a IIIF Presentation 3 (items) or 2 (sequences) manifest."""
    rows = []
    if 'items' in manifest:
        for c in manifest['items']:
            lab = c.get('label') or {}
            label = (lab.get('none') or lab.get('en') or ['?'])[0] if isinstance(lab, dict) else str(lab)
            body = c['items'][0]['items'][0]['body']
            svc = body.get('service')
            svc = svc[0] if isinstance(svc, list) else svc
            base = svc.get('@id') or svc.get('id')
            rows.append(dict(label=label, id=base.rstrip('/').rsplit('/', 1)[1], width=int(body.get('width') or c.get('width')), height=int(body.get('height') or c.get('height'))))
    else:
        for c in manifest['sequences'][0]['canvases']:
            lab = c.get('label')
            label = (lab.get('none') or lab.get('en') or ['?'])[0] if isinstance(lab, dict) else str(lab)
            res = c['images'][0]['resource']
            base = res['service']['@id']
            rows.append(dict(label=label, id=base.rstrip('/').rsplit('/', 1)[1], width=int(res.get('width') or c['width']), height=int(res.get('height') or c['height'])))
    return rows


def canvas_candidates(folio: str, rows: Sequence[dict]) -> List[str]:
    """Image ids of the canvases whose label mentions the folio's leaf and side (f70r1 -> '69v and 70r'; fRos -> the
    85v/86r foldout). Several candidates mean the registration decides."""
    if folio == 'fRos':
        return [r['id'] for r in rows if '85v' in r['label'] and '86r' in r['label']]
    m = FOLIO_RE.match(folio)
    if not m:
        return []
    want = (int(m.group(1)), m.group(2))
    out = []
    for r in rows:
        if any((int(a), b) == want for a, b in MENTION_RE.findall(r['label'])):
            out.append(r['id'])
    return out


def build_beinecke_index(manifest: Optional[dict] = None, folios: Optional[Sequence[str]] = None, out: Optional[Path] = None, log=print) -> dict:
    """Fetch the Yale manifest (or take one), index its canvases and map the toolkit's folios to them; write
    resources/beinecke_iiif.json. Returns the index."""
    if manifest is None:
        log('fetching ' + MANIFEST_URL)
        with urllib.request.urlopen(urllib.request.Request(MANIFEST_URL, headers={'User-Agent': USER_AGENT}), timeout=120) as r:
            manifest = json.load(r)
    rows = _canvas_rows(manifest)
    if folios is None:
        from .manuscript import Manuscript
        folios = [p['folio'] for p in Manuscript.load(extra=True).pages]
        from .audit.review import load_review
        for f in load_review()['pages']:
            if f not in folios:
                folios.append(f)
        if 'fRos' not in folios:
            folios.append('fRos')
    mapping, unmapped = {}, []
    for f in folios:
        c = canvas_candidates(f, rows)
        if c:
            mapping[f] = c
        else:
            unmapped.append(f)
    index = dict(manifest=MANIFEST_URL, built=date.today().isoformat(), credit=CREDIT, image_url=IIIF_BASE % '<id>' + '/full/full/0/default.jpg',
                 canvases=rows, folios=mapping, unmapped=sorted(unmapped))
    out = Path(out) if out else paths.resource(INDEX_FILE)
    out.write_text(json.dumps(index, indent=0, sort_keys=True) + '\n', encoding='utf-8')
    log('wrote %s: %d canvases, %d folios mapped (%d with several candidate canvases), %d unmapped' % (
        out, len(rows), len(mapping), sum(1 for v in mapping.values() if len(v) > 1), len(unmapped)))
    return index


_INDEX = {}


def beinecke_index() -> dict:
    """The stored index: {canvases: [{label, id, width, height}], folios: {folio: [image ids]}, unmapped: [...]}."""
    if 'index' not in _INDEX:
        p = paths.resource(INDEX_FILE)
        if not p.is_file():
            raise paths.DataMissing('%s is missing; run images.build_beinecke_index()' % p)
        _INDEX['index'] = json.loads(p.read_text(encoding='utf-8'))
    return _INDEX['index']


def canvas_info(image_id: str) -> Optional[dict]:
    for r in beinecke_index()['canvases']:
        if r['id'] == image_id:
            return r
    return None


def image_url(image_id: str, size: str = 'full') -> str:
    return (IIIF_BASE % image_id) + '/full/%s/0/default.jpg' % size


# ----------------------------------------------------------------------------- download
def _complete_jpeg(path: Path) -> bool:
    """True when the file decodes as a complete image (the IIIF server sends no Content-Length to compare with)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except (OSError, ValueError):
        return False


def _download(url: str, dest: Path, log=None, pause: float = PAUSE_S) -> int:
    """Download `url` to `dest` (temp file, then rename). An existing file that decodes completely is kept. Returns
    the file size. Sequential and polite: a pause after every request."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    last = None
    for attempt in range(RETRIES):
        try:
            if dest.is_file() and _complete_jpeg(dest):
                return dest.stat().st_size
            if log:
                log('downloading %s' % url)
            tmp = dest.with_suffix(dest.suffix + '.part')
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, 'wb') as f:
                shutil.copyfileobj(r, f, 1 << 16)
            os.replace(tmp, dest)
            time.sleep(pause)
            return dest.stat().st_size
        except (urllib.error.URLError, OSError) as err:
            last = err
            time.sleep(5 * (3 ** attempt))
    raise OSError('could not download %s: %s' % (url, last))


def _display_url(folio: str, review: Optional[dict] = None) -> Optional[str]:
    if review is None:
        from .audit.review import load_review
        review = load_review()
    return (review.get('pages', {}).get(folio) or {}).get('display_image')


def image_path(folio: str, source: str = 'beinecke', image_id: Optional[str] = None) -> Path:
    """Where the cached file of a page lives (whether or not it exists)."""
    if source == 'display':
        return cache_dir() / 'display' / ('%s.jpg' % folio)
    if image_id is None:
        image_id = resolved_image_id(folio)
    return cache_dir() / 'beinecke' / ('%s.jpg' % image_id)


def resolved_image_id(folio: str) -> str:
    """The canvas a folio is measured on: the registration's choice when it has been made, else the first candidate."""
    reg = _registration_cache('beinecke').get(folio)
    if reg and reg.get('image_id'):
        return reg['image_id']
    cands = beinecke_index()['folios'].get(folio)
    if not cands:
        raise KeyError('%s has no Beinecke canvas in the index' % folio)
    return cands[0]


def fetch_image(folio: str, source: str = 'beinecke', image_id: Optional[str] = None, log=None, review: Optional[dict] = None, pause: float = PAUSE_S) -> Path:
    """The cached file of one page image, downloaded when absent (or when its size differs from the server's)."""
    if source not in SOURCES:
        raise ValueError('source must be one of %r' % (SOURCES,))
    dest = image_path(folio, source, image_id)
    idx_path = _cache_index_path(source)
    index = _read_json(idx_path, {})
    rec = index.get(dest.name)
    if dest.is_file() and rec and rec.get('bytes') == dest.stat().st_size:
        return dest
    if source == 'display':
        url = _display_url(folio, review)
        if not url:
            raise paths.DataMissing('%s has no display image in the alignment review' % folio)
    else:
        url = image_url(image_id or resolved_image_id(folio))
    size = _download(url, dest, log, pause)
    index[dest.name] = dict(bytes=size, url=url, fetched=date.today().isoformat())
    _write_json(index, idx_path)
    return dest


def fetch_images(folios: Optional[Sequence[str]] = None, source: str = 'beinecke', log=print, pause: float = PAUSE_S, all_candidates: bool = True) -> dict:
    """Bulk download with progress. folios: default every page the index maps (beinecke) or every review page
    (display). For a folio with several candidate canvases every candidate is fetched (the registration picks one)."""
    from .audit.review import load_review
    review = load_review()
    if folios is None:
        folios = sorted(beinecke_index()['folios']) if source == 'beinecke' else sorted(review['pages'])
    done, failed, bytes_total = [], [], 0
    t0 = time.time()
    for k, f in enumerate(folios):
        ids = [None]
        if source == 'beinecke':
            cands = beinecke_index()['folios'].get(f, [])
            ids = cands if (all_candidates and len(cands) > 1) else [resolved_image_id(f)] if cands else []
            if not ids:
                failed.append('%s (no canvas)' % f)
                continue
        for iid in ids:
            try:
                p = fetch_image(f, source, iid, log=None, review=review, pause=pause)
                bytes_total += p.stat().st_size
                done.append(p.name)
            except (OSError, paths.DataMissing) as err:
                failed.append('%s (%s)' % (f, err))
        if log and (k % 10 == 9 or k == len(folios) - 1):
            log('  %d / %d pages, %.0f MB in the cache, %.0f s' % (k + 1, len(folios), bytes_total / 2 ** 20, time.time() - t0))
    return dict(fetched_or_present=len(set(done)), failed=failed, bytes=bytes_total, cache=str(cache_dir() / source))


def page_image(folio: str, source: str = 'beinecke', image_id: Optional[str] = None, log=None) -> np.ndarray:
    """The page image as an RGB uint8 array (downloaded on first use). 'beinecke': the full-resolution scan;
    'display': the Voynichese Project's 636 x 900 image."""
    from PIL import Image
    p = fetch_image(folio, source, image_id, log=log)
    im = Image.open(p)
    im.load()
    return np.asarray(im.convert('RGB'))


# ----------------------------------------------------------------------------- transforms
def _apply(M: np.ndarray, pts) -> np.ndarray:
    """Apply a 3x3 homogeneous matrix to N x 2 points."""
    P = np.asarray(pts, float).reshape(-1, 2)
    h = np.column_stack([P, np.ones(len(P))]) @ M.T
    return h[:, :2] / h[:, 2:3]


def _jacobian(M: np.ndarray, x: float, y: float) -> np.ndarray:
    """The 2x2 Jacobian of the mapping at (x, y)."""
    h = M @ np.array([x, y, 1.0])
    w = h[2]
    J = np.empty((2, 2))
    for j in range(2):
        J[0, j] = (M[0, j] * w - h[0] * M[2, j]) / (w * w)
        J[1, j] = (M[1, j] * w - h[1] * M[2, j]) / (w * w)
    return J


def local_scale(M: np.ndarray, x: float, y: float) -> float:
    return float(math.sqrt(abs(np.linalg.det(_jacobian(M, x, y)))))


def local_rotation_deg(M: np.ndarray, x: float, y: float) -> float:
    """The rotation (degrees, positive = clockwise on screen with y down) the mapping applies to a small horizontal
    segment at (x, y)."""
    J = _jacobian(M, x, y)
    return float(math.degrees(math.atan2(J[1, 0], J[0, 0])))


def display_transform(folio: str, review: Optional[dict] = None) -> dict:
    """Recorded frame -> display image (636 x 900), a least-squares affine on the centres of the review's rectangles
    (the display rectangles are the recorded ones scaled, rounded and padded by about 1.5 px a side). Returns
    {matrix, residual_px (RMS of the centre residuals in recorded-frame px), n, pad_px, method}."""
    if review is None:
        from .audit.review import load_review
        review = load_review()
    P, D = [], []
    for g in review['groups'].values():
        if g.get('page') != folio or not g.get('display_parts') or len(g['display_parts']) != len(g.get('parts') or []):
            continue
        for a, b in zip(g['parts'], g['display_parts']):
            if b[2] <= b[0] or b[3] <= b[1]:             # clipped to nothing: off the display image, which shows only part of f101v
                continue
            P.append(a)
            D.append(b)
    if len(P) < 3:
        return dict(matrix=None, residual_px=None, n=len(P), method='display-affine', ok=False, reason='fewer than 3 rectangles with display parts')
    P, D = np.array(P, float), np.array(D, float)
    pc = np.column_stack([(P[:, 0] + P[:, 2]) / 2, (P[:, 1] + P[:, 3]) / 2])
    dc = np.column_stack([(D[:, 0] + D[:, 2]) / 2, (D[:, 1] + D[:, 3]) / 2])
    A = np.column_stack([pc, np.ones(len(pc))])
    keep = np.ones(len(pc), bool)
    for _ in range(3):                                   # trimmed least squares: a few groups carry display parts of another frame
        cx = np.linalg.lstsq(A[keep], dc[keep, 0], rcond=None)[0]
        cy = np.linalg.lstsq(A[keep], dc[keep, 1], rcond=None)[0]
        res = np.column_stack([A @ cx - dc[:, 0], A @ cy - dc[:, 1]])
        new_keep = np.hypot(res[:, 0], res[:, 1]) <= DISPLAY_TRIM_PX
        if new_keep.sum() < 3 or np.array_equal(new_keep, keep):
            break
        keep = new_keep
    M = np.array([[cx[0], cx[1], cx[2]], [cy[0], cy[1], cy[2]], [0.0, 0.0, 1.0]])
    scale = math.sqrt(abs(cx[0] * cy[1] - cx[1] * cy[0]))
    rms_frame = float(np.sqrt(np.mean(res[keep] ** 2)) * math.sqrt(2) / scale)
    pad = float(np.median(np.concatenate([((D[keep, 2] - D[keep, 0]) - cx[0] * (P[keep, 2] - P[keep, 0])) / 2, ((D[keep, 3] - D[keep, 1]) - cy[1] * (P[keep, 3] - P[keep, 1])) / 2])))
    n_out = int((~keep).sum())
    ok = rms_frame < DISPLAY_MAX_RESIDUAL_PX and keep.sum() >= max(3, 0.6 * len(keep))
    return dict(matrix=M.tolist(), residual_px=rms_frame, n=int(len(P)), n_outliers=n_out, pad_px=pad, scale=scale, method='display-affine', ok=bool(ok),
                reason=None if ok else 'display rectangles inconsistent with one affine (%d of %d kept, rms %.1f px)' % (int(keep.sum()), len(keep), rms_frame))


# ----------------------------------------------------------------------------- registration
_PRODUCT = {}


def registration_product(path=None, reload: bool = False) -> Optional[dict]:
    """The shipped registrations (``PRODUCT_KEY``), read once: {version, built, frame, warp, source, note, sources:
    {beinecke: {folio: record}, display: {folio: record}}}; None when the product is absent."""
    key = str(path) if path else ''
    if reload or key not in _PRODUCT:
        p = Path(path) if path else paths.resolve(PRODUCT_KEY, required=False)
        if p is None or not Path(p).is_file():
            _PRODUCT[key] = None
        else:
            from .bundle import read_json
            _PRODUCT[key] = read_json(p)
    return _PRODUCT[key]


def _product_record(folio: str, source: str) -> Optional[dict]:
    prod = registration_product()
    if not prod:
        return None
    rec = (prod.get('sources') or {}).get(source, {}).get(folio)
    return dict(rec) if rec else None


def _registration_cache(source: str) -> dict:
    return _read_json(cache_dir() / ('registration_%s.json' % source), {})


def build_registration_product(out=None, sources: Sequence[str] = SOURCES, log=print) -> dict:
    """Write the registrations data product from the cache: every record of the current REGISTRATION_VERSION, numbers
    only (PRODUCT_FIELDS). Returns the product."""
    from .bundle import write_json
    prod = dict(version=PRODUCT_VERSION, registration_version=REGISTRATION_VERSION, built=date.today().isoformat(), frame='recorded', warp='recorded', source='voynichese',
                maps_to='image pixels of the named source (beinecke: the Yale IIIF scan named by image_id; display: the Voynichese display image, 636 x 900)',
                note='Recorded frame -> page image, per page and source: a 3x3 matrix (recorded px -> image px), the median reprojection error of the inlier matches in recorded px, '
                     'inlier counts, the quadratic residual field (display px -> small-scan px), the local shift per bundle line (image px, added after the matrix) and quality flags. '
                     'Two photographs of one page do not share a warp beyond this residual field (docs/DATA_MODEL.md).',
                credit=CREDIT, sources={})
    counts = {}
    for s in sources:
        recs = {}
        for folio, rec in sorted(_registration_cache(s).items()):
            if rec.get('version') != REGISTRATION_VERSION:
                continue
            r = {k: rec.get(k) for k in PRODUCT_FIELDS if k in rec}
            r['flags'] = quality_flags(rec)
            recs[folio] = r
        prod['sources'][s] = recs
        counts[s] = dict(pages=len(recs), ok=sum(1 for r in recs.values() if r.get('ok')))
    prod['counts'] = counts
    out = Path(out) if out else paths.data_dir() / PRODUCT_KEY
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(prod, out)
    _PRODUCT.clear()
    if log:
        log('wrote %s (%.2f MB): %s' % (out, out.stat().st_size / 2 ** 20, ', '.join('%s %d pages (%d ok)' % (s, c['pages'], c['ok']) for s, c in counts.items())))
    return prod


def _save_registration(source: str, folio: str, rec: dict):
    path = cache_dir() / ('registration_%s.json' % source)
    cache = _read_json(path, {})
    cache[folio] = rec
    _write_json(cache, path)


def _gray(rgb: np.ndarray) -> np.ndarray:
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.uint8)


def _downscale(gray: np.ndarray, factor: int) -> np.ndarray:
    import cv2
    h, w = gray.shape
    return cv2.resize(gray, (w // factor, h // factor), interpolation=cv2.INTER_AREA)


def _sift_match(img_a: np.ndarray, img_b: np.ndarray, nfeatures: int = 12000, ratio: float = 0.75):
    """SIFT keypoints of two grayscale images, matched with the ratio test. Returns (src N x 2, dst N x 2)."""
    import cv2
    sift = cv2.SIFT_create(nfeatures=nfeatures)
    k1, d1 = sift.detectAndCompute(img_a, None)
    k2, d2 = sift.detectAndCompute(img_b, None)
    if d1 is None or d2 is None or len(k1) < 8 or len(k2) < 8:
        return np.zeros((0, 2)), np.zeros((0, 2))
    bf = cv2.BFMatcher(cv2.NORM_L2)
    good = []
    for pair in bf.knnMatch(d1, d2, k=2):
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance:
            good.append(pair[0])
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    return src.reshape(-1, 2), dst.reshape(-1, 2)


def _fit_homography(src: np.ndarray, dst: np.ndarray, threshold: float):
    """Homography (or similarity when inliers are few) by RANSAC. Returns (3x3, inlier mask, method) or (None, None, 'failed')."""
    import cv2
    if len(src) >= 4:
        Hm, mask = cv2.findHomography(src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2), cv2.RANSAC, threshold)
        if Hm is not None and mask is not None and int(mask.sum()) >= MIN_INLIERS_HOMOGRAPHY:
            return Hm, mask.ravel() > 0, 'sift-homography'
    if len(src) >= 3:
        Am, mask = cv2.estimateAffinePartial2D(src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2), method=cv2.RANSAC, ransacReprojThreshold=threshold)
        if Am is not None and mask is not None and int(mask.sum()) >= MIN_INLIERS_SIMILARITY:
            return np.vstack([Am, [0.0, 0.0, 1.0]]), mask.ravel() > 0, 'sift-similarity'
    return None, None, 'failed'


def _quadratic_field(xy: np.ndarray, r: np.ndarray, iterations: int = 4):
    """Coefficients of a 2-D quadratic (1, x, y, x^2, xy, y^2) fitted to each residual component with Huber weights."""
    X = np.column_stack([np.ones(len(xy)), xy[:, 0], xy[:, 1], xy[:, 0] ** 2, xy[:, 0] * xy[:, 1], xy[:, 1] ** 2])
    coef = np.zeros((2, 6))
    for j in range(2):
        w = np.ones(len(xy))
        c = np.zeros(6)
        for it in range(iterations + 1):
            sw = np.sqrt(w)
            c, *_ = np.linalg.lstsq(X * sw[:, None], r[:, j] * sw, rcond=None)
            if it == iterations:
                break
            e = r[:, j] - X @ c
            scale = 1.4826 * np.median(np.abs(e - np.median(e))) + 1e-9
            w = np.minimum(1.0, 1.345 * scale / np.maximum(np.abs(e), 1e-12))
        coef[j] = c
    return coef


def _eval_field(coef: np.ndarray, xy) -> np.ndarray:
    xy = np.asarray(xy, float).reshape(-1, 2)
    X = np.column_stack([np.ones(len(xy)), xy[:, 0], xy[:, 1], xy[:, 0] ** 2, xy[:, 0] * xy[:, 1], xy[:, 1] ** 2])
    return X @ coef.T


def _line_boxes(app, ms, folio: str) -> Dict[str, List[list]]:
    """{locus: [recorded boxes]} of a page's located rectangles (one per rectangle)."""
    from .geometry import line_units
    units = line_units(app, ms)
    pages = ms.pages if hasattr(ms, 'pages') else ms['pages']
    out = {}
    for p in pages:
        if p.get('folio') == folio:
            for l in range(p['start_line'], p['end_line']):
                if units[l]:
                    out[str(app['lines'][l]['locus'])] = [u['box'] for u in units[l]]
    return out


def registration(folio: str, source: str = 'beinecke', app=None, ms=None, review: Optional[dict] = None, force: bool = False, log=None) -> dict:
    """Recorded frame -> image pixels for one page (module docstring). Returns the cached record when present:
    {folio, source, ok, method, matrix (3x3, recorded -> image px), residual_px (median reprojection error of the
    inlier matches, recorded-frame px), n_inliers, n_matches, scale (image px per recorded px at the page centre),
    rotation_deg, image_id, image_size, display (the display affine's record), lines {locus: {dx, dy (local shift in
    image px added after the matrix), n, from ('inliers' | 'field')}}, field (quadratic coefficients of the residual
    field, image px), shift_range_px (max - min of the lines' shifts, recorded-frame px), flags, version}.
    `app` and `ms` (the sensitivity bundle and the manuscript) give the lines for the local shifts; without them the
    local shifts come from the field alone."""
    if source not in SOURCES:
        raise ValueError('source must be one of %r' % (SOURCES,))
    if not force:
        # the shipped product first; the cache for a page the product lacks
        rec = _product_record(folio, source)
        if rec and rec.get('version') == REGISTRATION_VERSION and (source == 'display' or rec.get('lines') or app is None):
            rec['flags'] = quality_flags(rec)
            return rec
    cache = _registration_cache(source)
    rec = cache.get(folio)
    if rec and not force and rec.get('version') == REGISTRATION_VERSION and (source == 'display' or rec.get('lines') or app is None):
        rec['flags'] = quality_flags(rec)
        return rec
    if review is None:
        from .audit.review import load_review
        review = load_review()
    disp = display_transform(folio, review)
    rec = dict(folio=folio, source=source, version=REGISTRATION_VERSION, ok=False, method=None, matrix=None, residual_px=None, n_inliers=0, n_matches=0,
               flags=[], display=disp, lines={}, computed=date.today().isoformat())
    if not disp.get('ok'):
        rec['flags'].append('display_transform_failed')
        rec['method'] = 'failed'
        _save_registration(source, folio, rec)
        return rec
    A = np.array(disp['matrix'])
    if source == 'display':
        rec.update(ok=True, method=disp['method'], matrix=disp['matrix'], residual_px=disp['residual_px'], n_inliers=disp['n'], n_matches=disp['n'],
                   scale=disp['scale'], rotation_deg=local_rotation_deg(A, 500, 750), image_size=[636, 900])
        _save_registration(source, folio, rec)
        return rec
    # beinecke: SIFT between the display image and each candidate scan at one third scale
    try:
        disp_img = page_image(folio, 'display', log=log)
    except (OSError, paths.DataMissing) as err:
        rec['flags'].append('no_display_image: %s' % err)
        rec['method'] = 'failed'
        _save_registration(source, folio, rec)
        return rec
    disp_gray = _gray(disp_img)
    cands = beinecke_index()['folios'].get(folio, [])
    if not cands:
        rec['flags'].append('no_canvas')
        rec['method'] = 'failed'
        _save_registration(source, folio, rec)
        return rec
    best = None
    tried = []

    def attempt(iid):
        nonlocal best
        try:
            scan = page_image(folio, 'beinecke', iid, log=log)
        except OSError as err:
            rec['flags'].append('download_failed %s: %s' % (iid, err))
            return
        small = _downscale(_gray(scan), SCAN_FACTOR)
        src, dst = _sift_match(disp_gray, small)
        Hm, inl, method = _fit_homography(src, dst, RANSAC_PX)
        n_inl = int(inl.sum()) if inl is not None else 0
        tried.append((iid, int(len(src)), n_inl))
        if log:
            log('  %s canvas %s: %d matches, %d inliers (%s)' % (folio, iid, len(src), n_inl, method))
        if best is None or n_inl > best[0]:
            best = (n_inl, iid, Hm, inl, method, src, dst, scan.shape[:2])
    for iid in cands:
        attempt(iid)
    if best is None or best[2] is None:
        # the manifest's labels are not always right for foldout parts: try the canvases next to the candidates
        rows = beinecke_index()['canvases']
        pos = [k for k, r in enumerate(rows) if r['id'] in cands]
        for k in sorted({k + d for k in pos for d in (-2, -1, 1, 2)}):
            if 0 <= k < len(rows) and rows[k]['id'] not in cands and rows[k]['label'][0].isdigit():
                attempt(rows[k]['id'])
        if best is not None and best[2] is not None:
            rec['flags'].append('canvas_from_neighbour_search')
    if best is None or best[2] is None:
        rec['flags'].append('sift_failed')
        rec['method'] = 'failed'
        rec['n_matches'] = int(len(best[5])) if best else 0
        _save_registration(source, folio, rec)
        return rec
    n_inl, iid, Hm, inl, method, src, dst, shape = best
    S = np.array([[SCAN_FACTOR, 0, (SCAN_FACTOR - 1) / 2.0], [0, SCAN_FACTOR, (SCAN_FACTOR - 1) / 2.0], [0, 0, 1.0]])
    M = S @ Hm @ A                                           # recorded -> full scan px
    MA = Hm @ A                                              # recorded -> small scan px
    # residuals of the inliers at the small scale: the local warp difference between the two photographs
    src_i, dst_i = src[inl], dst[inl]
    proj = _apply(Hm, src_i)
    r_small = dst_i - proj                                   # small-scan px
    cx, cy = 568.0, 750.0                                    # the recorded frame's centre, roughly
    scale_small = local_scale(MA, cx, cy)                    # small px per recorded px
    scale_full = local_scale(M, cx, cy)
    resid_frame = float(np.median(np.hypot(r_small[:, 0], r_small[:, 1])) / scale_small)
    field = _quadratic_field(src_i, r_small)                 # residual as a function of the display position
    # per line: the median residual of the inliers around the line (display frame), else the field at the line's centre
    lines = {}
    shifts = []
    if app is not None and ms is not None:
        boxes = _line_boxes(app, ms, folio)
        H_disp = float(np.median([b[3] - b[1] for bs in boxes.values() for b in bs])) * disp['scale'] if boxes else 20.0
        for locus, bs in boxes.items():
            d = _apply(A, np.array([[b[0], b[1]] for b in bs] + [[b[2], b[3]] for b in bs]))
            x0, y0, x1, y1 = d[:, 0].min(), d[:, 1].min(), d[:, 0].max(), d[:, 1].max()
            near = (src_i[:, 0] >= x0 - H_disp) & (src_i[:, 0] <= x1 + H_disp) & (src_i[:, 1] >= y0 - 0.5 * H_disp) & (src_i[:, 1] <= y1 + 0.5 * H_disp)
            centre = [[(x0 + x1) / 2, (y0 + y1) / 2]]
            if int(near.sum()) >= LINE_MIN_INLIERS:
                dx, dy = np.median(r_small[near, 0]), np.median(r_small[near, 1])
                origin = 'inliers'
            else:
                dx, dy = _eval_field(field, centre)[0]
                origin = 'field'
            lines[locus] = dict(dx=float(dx * SCAN_FACTOR), dy=float(dy * SCAN_FACTOR), n=int(near.sum()), source=origin)
            shifts.append((dx * SCAN_FACTOR / scale_full, dy * SCAN_FACTOR / scale_full))
    sh = np.array(shifts) if shifts else np.zeros((0, 2))
    rec.update(ok=True, method=method, matrix=M.tolist(), residual_px=resid_frame, n_inliers=n_inl, n_matches=int(len(src)), scale=scale_full,
               rotation_deg=local_rotation_deg(M, cx, cy), image_id=iid, image_size=[int(shape[1]), int(shape[0])], candidates=cands, tried=tried,
               field=field.tolist(), field_frame='display px -> small scan px residual', lines=lines,
               shift_range_px=[float(np.ptp(sh[:, 0])) if len(sh) else 0.0, float(np.ptp(sh[:, 1])) if len(sh) else 0.0],
               shift_median_px=[float(np.median(sh[:, 0])) if len(sh) else 0.0, float(np.median(sh[:, 1])) if len(sh) else 0.0],
               field_amplitude_px=_field_amplitude(field, A, scale_full, disp.get('scale', 1.0)))
    rec['flags'] = quality_flags(rec)
    _save_registration(source, folio, rec)
    return rec


def quality_flags(rec: dict) -> List[str]:
    """The quality flags of a registration record, from its numbers: similarity_fallback, few_inliers (under 200),
    large_residual (median reprojection error above LARGE_RESIDUAL_PX recorded px), large_shift_range (the per-line
    shifts span more than 6 recorded px), large_median_shift (above 4 px). Recomputed on load, so a cached record
    follows the current thresholds."""
    if not rec.get('ok'):
        return list(rec.get('flags') or [])
    flags = [f for f in (rec.get('flags') or []) if f.startswith(('no_', 'download', 'display_transform', 'canvas_from'))]
    if rec.get('method') == 'sift-similarity':
        flags.append('similarity_fallback')
    if rec.get('source') == 'beinecke' and (rec.get('n_inliers') or 0) < FEW_INLIERS:
        flags.append('few_inliers')
    if (rec.get('residual_px') or 0.0) > LARGE_RESIDUAL_PX:
        flags.append('large_residual')
    sr = rec.get('shift_range_px') or [0.0, 0.0]
    if max(sr) > 6.0:
        flags.append('large_shift_range')
    sm = rec.get('shift_median_px') or [0.0, 0.0]
    if math.hypot(sm[0], sm[1]) > 4.0:
        flags.append('large_median_shift')
    return flags


def _field_amplitude(field: np.ndarray, A: np.ndarray, scale_full: float, scale_disp: float) -> List[float]:
    """Peak-to-peak of the residual field over the display image (recorded-frame px), per component."""
    g = np.array([[x, y] for x in np.linspace(40, 596, 8) for y in np.linspace(40, 860, 10)])
    v = _eval_field(np.asarray(field), g) * SCAN_FACTOR / scale_full
    return [float(np.ptp(v[:, 0])), float(np.ptp(v[:, 1]))]


def registrations(source: str = 'beinecke') -> dict:
    """Every registration record of a source: the shipped product's, with the cache's for pages it lacks (flags
    recomputed from the numbers)."""
    out = {}
    prod = registration_product()
    if prod:
        out.update({k: dict(v) for k, v in (prod.get('sources') or {}).get(source, {}).items()})
    for folio, rec in _registration_cache(source).items():
        if folio not in out:
            out[folio] = rec
    for rec in out.values():
        rec['flags'] = quality_flags(rec)
    return out


class Mapping:
    """The mapping of one page from the recorded frame to image pixels (matrix plus an optional per-line shift, the
    line named by its locus)."""

    def __init__(self, rec: dict, line=None):
        if not rec.get('ok'):
            raise ValueError('registration of %s (%s) failed: %s' % (rec.get('folio'), rec.get('source'), rec.get('flags')))
        self.rec = rec
        self.M = np.array(rec['matrix'], float)
        self.Minv = np.linalg.inv(self.M)
        sh = (rec.get('lines') or {}).get(str(line)) if line is not None else None
        self.shift = np.array([sh['dx'], sh['dy']]) if sh else np.zeros(2)
        self.line = line

    def to_image(self, pts) -> np.ndarray:
        return _apply(self.M, pts) + self.shift

    def to_frame(self, pts) -> np.ndarray:
        return _apply(self.Minv, np.asarray(pts, float).reshape(-1, 2) - self.shift)

    def scale(self, x: float, y: float) -> float:
        return local_scale(self.M, x, y)

    def rotation_deg(self, x: float, y: float) -> float:
        return local_rotation_deg(self.M, x, y)

    def box_to_image(self, box) -> np.ndarray:
        """Axis-aligned image-pixel bounds [X0, Y0, X1, Y1] of a recorded rectangle's four mapped corners."""
        c = self.to_image([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]])
        return np.array([c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max()])


def region(folio: str, box, pad=(6.0, 8.0), source: str = 'beinecke', line=None, image: Optional[np.ndarray] = None, rec: Optional[dict] = None) -> dict:
    """The image region of a recorded rectangle, in memory: {array (RGB), origin [X0, Y0] (image px of the region's
    top-left), box_px [x0, y0, x1, y1] (the mapped rectangle in region coordinates), mapping (Mapping), to_frame(pts)
    (region px -> recorded frame), scale, rotation_deg}. `pad` is in recorded-frame px (x, y)."""
    rec = rec or registration(folio, source)
    m = Mapping(rec, line)
    if image is None:
        image = page_image(folio, source, rec.get('image_id'))
    b = m.box_to_image(box)
    s = m.scale((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    px, py = pad[0] * s, pad[1] * s
    X0, Y0 = int(math.floor(b[0] - px)), int(math.floor(b[1] - py))
    X1, Y1 = int(math.ceil(b[2] + px)), int(math.ceil(b[3] + py))
    X0c, Y0c = max(0, X0), max(0, Y0)
    X1c, Y1c = min(image.shape[1], X1), min(image.shape[0], Y1)
    arr = image[Y0c:Y1c, X0c:X1c]
    origin = np.array([X0c, Y0c], float)

    def to_frame(pts):
        return m.to_frame(np.asarray(pts, float).reshape(-1, 2) + origin)
    return dict(array=arr, origin=origin.tolist(), box_px=(b - np.array([X0c, Y0c, X0c, Y0c])).tolist(), mapping=m, to_frame=to_frame, scale=s,
                rotation_deg=m.rotation_deg((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), clipped=bool(X0c != X0 or Y0c != Y0 or X1c != X1 or Y1c != Y1))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Download page images into the cache (%s).' % cache_dir())
    ap.add_argument('--source', default='beinecke', choices=SOURCES)
    ap.add_argument('--folios', help='comma-separated folios (default: every mapped page)')
    ap.add_argument('--build-index', action='store_true', help='rebuild resources/beinecke_iiif.json from the Yale manifest first')
    args = ap.parse_args(argv)
    if args.build_index:
        build_beinecke_index()
    res = fetch_images(args.folios.split(',') if args.folios else None, args.source)
    print('%d files present in %s (%.0f MB); %d failed' % (res['fetched_or_present'], res['cache'], res['bytes'] / 2 ** 20, len(res['failed'])))
    for f in res['failed']:
        print('  failed: ' + f)
    return 1 if res['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
