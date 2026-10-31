"""Coordinate frames, warp states and sources: the three tags every coordinate-bearing table carries.

The toolkit holds several coordinate sets of the same words: the recorded rectangles under two policies, the same
rectangles with each page's photographic warp removed, baseline points under four methods, ink measurements mapped
from a second photograph, and the Rosettes' detected boxes in their own image. Combining two of them is only
meaningful when they share a frame and a warp state, and nothing used to enforce it (a writing-order effect measured
in the recorded frame turned out to be half page sag). Every table therefore carries, at top level,

    frame    'recorded'  the Voynichese XML pixel frame of each page (also 'detected' for a page whose boxes were found
                         on another image: fRos on the toolkit's quarter-scale Beinecke copy, named in `frame_image`;
                         a bundle lists such pages in `detected_pages`); 'display' marks coordinates moved for
                         display only (``wheels.centered_layout``: every wheel translated to a common centre), which
                         are not measured geometry and can be combined with nothing else
    warp     'recorded'  the page warp of the photograph is still in the coordinates
             'flat'      the shared page warp of ``vmsspatial.warp`` has been removed
    source   where the numbers were measured: 'voynichese' (the recorded rectangles), 'beinecke' (the scans),
             'display' (the Voynichese display image), 'synthetic' (typeset by the toolkit), 'detected' (found on an
             image by the toolkit)

``tags(obj)`` reads them (a table without tags is recorded / recorded / voynichese, the state every table was in
before the tags existed; a bundle's ``geometry_kind`` fills them in), ``require_same(a, b, what)`` raises
``FrameError`` when two tables about to be combined differ in frame or warp. The source may differ: the registration
(``images``, the data product ``registrations.json.gz``) maps a Beinecke measurement into the recorded frame to about
one recorded pixel plus the per-line residual, which is what the frame tag guarantees and all it guarantees; two
photographs do not share a warp beyond that residual field (docs/DATA_MODEL.md).

``to_image`` / ``to_recorded`` move points between the recorded frame and a page image through the stored
registration.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

FRAMES = ('recorded', 'detected', 'display')     # 'display': a display transform's coordinates (centred wheels), never measured geometry
WARPS = ('recorded', 'flat')
SOURCES = ('voynichese', 'beinecke', 'display', 'synthetic', 'detected')
TAG_KEYS = ('frame', 'warp', 'source')
DEFAULT_TAGS = dict(frame='recorded', warp='recorded', source='voynichese')
_KIND_TAGS = {'recorded': dict(frame='recorded', warp='recorded', source='voynichese'),
              'flattened': dict(frame='recorded', warp='flat', source='voynichese'),
              'synthetic': dict(frame='recorded', warp='recorded', source='synthetic'),
              'detected': dict(frame='detected', warp='recorded', source='detected')}


class FrameError(ValueError):
    """Two coordinate sets that do not share a frame or a warp state were about to be combined."""


class FrameWarning(UserWarning):
    """Two coordinate sets differ in warp state, and the function combines them by a rule that stays coherent (an ink
    baseline travels with its own box bottom) or does not read the second set's positions; said aloud anyway."""


def _check(tag: dict):
    if tag['frame'] not in FRAMES:
        raise FrameError('unknown frame %r (one of %s)' % (tag['frame'], ', '.join(FRAMES)))
    if tag['warp'] not in WARPS:
        raise FrameError('unknown warp state %r (one of %s)' % (tag['warp'], ', '.join(WARPS)))
    if tag['source'] not in SOURCES:
        raise FrameError('unknown source %r (one of %s)' % (tag['source'], ', '.join(SOURCES)))


def tags(obj) -> Dict[str, object]:
    """The frame, warp and source of a table (a dict): its own tags, else those implied by its ``geometry_kind``,
    else recorded / recorded / voynichese. Also `detected_pages` (pages in the detected frame inside a recorded-frame
    bundle) and `frame_image` when the table names one."""
    if obj is None:
        raise FrameError('no table to read the frame tags from')
    if not isinstance(obj, dict) and isinstance(getattr(obj, 'meta', None), dict):
        obj = obj.meta                                       # a table of records (``compare.Records``) carries its tags in its metadata
    if not isinstance(obj, dict):
        raise FrameError('frame tags live on a dict table; got %s' % type(obj).__name__)
    base = dict(_KIND_TAGS.get(obj.get('geometry_kind'), DEFAULT_TAGS))
    for k in TAG_KEYS:
        if obj.get(k) is not None:
            base[k] = obj[k]
    # older products wrote a sentence into `frame` ("recorded (the Voynichese XML pixel frame ...)", "flattened (...)")
    if isinstance(base['frame'], str) and base['frame'] not in FRAMES:
        low = base['frame'].lower()
        if low.startswith('flattened'):
            base['frame'], base['warp'] = 'recorded', 'flat'
        elif low.startswith('recorded'):
            base['frame'] = 'recorded'
    _check(base)
    out = dict(base)
    out['detected_pages'] = tuple(obj.get('detected_pages') or ())
    if obj.get('frame_image'):
        out['frame_image'] = obj['frame_image']
    return out


def describe(obj) -> str:
    t = tags(obj)
    s = '%s frame, %s warp, source %s' % (t['frame'], t['warp'], t['source'])
    if t['detected_pages']:
        s += ' (detected frame on %s)' % ', '.join(t['detected_pages'])
    return s


def tag(obj: dict, frame: Optional[str] = None, warp: Optional[str] = None, source: Optional[str] = None, frame_image: Optional[str] = None) -> dict:
    """Set the tags on a table IN PLACE (missing ones from ``tags(obj)``) and return it."""
    cur = tags(obj)
    obj['frame'] = frame or cur['frame']
    obj['warp'] = warp or cur['warp']
    obj['source'] = source or cur['source']
    if frame_image:
        obj['frame_image'] = frame_image
    _check(obj)
    return obj


def tagged(obj: dict, **kw) -> dict:
    """A shallow copy of a table with the tags set (``tag`` on a copy)."""
    return tag(dict(obj), **kw)


def ensure_tags(obj: dict) -> dict:
    """A table without tags gets the ones it implies, in place (the loader's step). Returns the table."""
    return tag(obj)


def require_same(a, b, what: str = 'these tables', keys: Iterable[str] = ('frame', 'warp')) -> Dict[str, object]:
    """Raise ``FrameError`` unless the two tables agree in every tag of `keys` (frame and warp by default: the source
    may differ, the registration having put the numbers into one frame). Returns the shared tags."""
    ta, tb = tags(a), tags(b)
    bad = [k for k in keys if ta[k] != tb[k]]
    if bad:
        raise FrameError('%s cannot be combined: the first is in the %s frame in the %s warp state (source %s), the second in the %s frame in the %s warp state (source %s); they differ in %s.'
                         % (what, ta['frame'], ta['warp'], ta['source'], tb['frame'], tb['warp'], tb['source'], ' and '.join(bad)))
    if ta['detected_pages'] != tb['detected_pages'] and 'frame' in keys and ta['detected_pages'] and tb['detected_pages']:
        raise FrameError('%s cannot be combined: they place different pages in the detected frame (%s against %s).' % (what, ta['detected_pages'], tb['detected_pages']))
    return ta


def check_same(a, b, what: str = 'these tables', keys: Iterable[str] = ('frame', 'warp')) -> Dict[str, object]:
    """``require_same`` as a warning: used where the combination stays coherent whatever the warp state (the ink
    product's baselines are stored relative to their own box bottoms) or where the second table's positions are not
    read. Returns the first table's tags."""
    import warnings
    try:
        return require_same(a, b, what, keys)
    except FrameError as err:
        warnings.warn(str(err) + ' The values are combined through the box bottoms, which is coherent, but say which warp state your numbers are in.', FrameWarning, stacklevel=3)
        return tags(a)


def require_warp(obj, warp: str, what: str = 'this table'):
    """Raise ``FrameError`` unless the table is in the named warp state."""
    t = tags(obj)
    if t['warp'] != warp:
        raise FrameError('%s must be in the %s warp state, but it is %s (frame %s, source %s).' % (what, warp, t['warp'], t['frame'], t['source']))
    return t


def require_recorded(obj, what: str = 'this table'):
    """Raise unless the table is recorded / recorded (what an overlay on the page image needs)."""
    t = tags(obj)
    if t['frame'] != 'recorded' or t['warp'] != 'recorded':
        raise FrameError('%s must be in the recorded frame and the recorded warp state to be drawn on the page image, but it is %s / %s (source %s).' % (what, t['frame'], t['warp'], t['source']))
    return t


# ----------------------------------------------------------------------------- moving points through the registration
def to_image(folio: str, pts, source: str = 'beinecke', line=None):
    """Recorded-frame points (N x 2) -> pixels of the page image of `source`, through the stored registration
    (``images.registration``; the data product first). `line` is the bundle line index whose local shift applies."""
    from .images import registration, Mapping
    return Mapping(registration(folio, source), line).to_image(pts)


def to_recorded(folio: str, pts, source: str = 'beinecke', line=None):
    """Image pixels (N x 2) of the page image of `source` -> the recorded frame (recorded warp state)."""
    from .images import registration, Mapping
    return Mapping(registration(folio, source), line).to_frame(pts)
