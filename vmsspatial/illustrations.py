"""Compact, registered manuscript-image overlays for articles and notebooks.

Pass the boxes actually used by the analysis. This module never selects sources
or changes analytical geometry. Requires the toolkit's images extra.

The image is a photograph, so only recorded coordinates sit on it. ``load_bundle``
gives flat coordinates by default, and a flat box lands up to 46 px away from its
word with nothing to show for it, so every call must say which state its boxes are
in: ``warp='recorded'``. Flat boxes are refused; ``warp.transform(bundle, 'recorded')``
or ``load_bundle(..., warp='recorded')`` gives the recorded ones.
"""
from __future__ import annotations
import argparse
import base64
import io
import json
from html import escape
from pathlib import Path
import numpy as np
from vmsspatial.frames import FrameError


def _require_recorded(warp):
    """The guard: a photograph takes recorded coordinates, and the caller has to say that is what it holds."""
    if warp == 'recorded':
        return
    if warp == 'flat':
        raise FrameError("image_overlay: flat boxes do not sit on the photograph; use warp.transform(bundle, 'recorded') or load_bundle(..., warp='recorded') and pass warp='recorded'")
    raise FrameError("image_overlay: say which warp state the boxes are in with warp='recorded'; load_bundle gives flat coordinates by default, and those do not sit on the photograph")


def image_overlay(folio, words, *, warp=None, source='beinecke', pad=18, max_width=1800,
                  image=None, registration=None):
    """Return (PIL crop, JSON-ready overlay) in one shared crop-pixel frame.

    words: [{id, label, box:[x0,y0,x1,y1], line:locus, role, value(optional)}]. `line` names the word's line on the
    page by its ZL locus, the key of the registration's local shifts.
    warp: 'recorded', stated by the caller: anything else raises FrameError (see the module note).
    Mapping uses the four corners and each line's local registration shift.
    The crop is a display product; original boxes are returned unchanged.
    """
    from PIL import Image
    from vmsspatial import images
    _require_recorded(warp)
    if not words or pad < 0 or max_width < 1:
        raise ValueError('Nonempty words, nonnegative padding and positive width required')
    rec = registration if registration is not None else images.registration(folio, source)
    if rec.get('folio') != folio or rec.get('source') != source:
        raise ValueError('Registration belongs to a different folio or image source')
    if image is None:
        image = images.page_image(folio, source, rec.get('image_id'))
    rgb = np.asarray(image)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expected an RGB image')
    rows = []
    ids = set()
    for word in words:
        box = np.asarray(word['box'], float)
        if box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2]):
            raise ValueError('Every box needs four finite coordinates and positive area')
        if word['id'] in ids:
            raise ValueError('Overlay IDs must be unique')
        ids.add(word['id'])
        if rec.get('lines') and str(word.get('line')) not in rec['lines']:
            raise ValueError('Missing local registration for the specified line')
        corners = [[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]
        polygon = images.Mapping(rec, word.get('line')).to_image(corners)
        rows.append(dict(word, polygon=polygon.tolist()))
    points = np.concatenate([r['polygon'] for r in rows])
    lo = np.maximum(0, np.floor(points.min(axis=0)-pad)).astype(int)
    hi = np.minimum([rgb.shape[1],rgb.shape[0]], np.ceil(points.max(axis=0)+pad)).astype(int)
    if np.any(hi <= lo):
        raise ValueError('All requested boxes lie outside the image')
    crop = Image.fromarray(rgb[lo[1]:hi[1],lo[0]:hi[0]])
    original_size = np.array(crop.size)
    if crop.width > max_width:
        crop = crop.resize((int(max_width), max(1,round(crop.height*max_width/crop.width))), Image.Resampling.LANCZOS)
    scale = np.array(crop.size)/original_size
    for row in rows:
        row['polygon'] = ((np.asarray(row['polygon'])-lo)*scale).round(4).tolist()
    return crop, dict(folio=folio, warp='recorded', width=crop.width, height=crop.height, words=rows,
                     registration=dict(source=source, method=rec.get('method'), residual_px=rec.get('residual_px'),
                                       flags=rec.get('flags',[]), local_line_shifts=bool(rec.get('lines'))),
                     crop_origin=lo.tolist(), display_scale=scale.tolist(),
                     credit=images.CREDIT if source=='beinecke' else 'The Voynichese Project; manuscript: Yale, Beinecke MS 408',
                     image_url=(images.IIIF_BASE % rec['image_id'] + '/full/full/0/default.jpg') if source=='beinecke' else None)


COLORS = dict(context='#64748b', candidate='#087f8c', target='#e47716', source='#8b3fb2')


def overlay_svg(image, overlay, *, title='Manuscript word boxes', labels=False):
    """Self-contained SVG: actual pixels plus registered, inspectable polygons."""
    stream=io.BytesIO();image.save(stream,format='JPEG',quality=90)
    content=base64.b64encode(stream.getvalue()).decode('ascii')
    w,h=overlay['width'],overlay['height']
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img"><title>{escape(title)}</title>',
           f'<image width="{w}" height="{h}" href="data:image/jpeg;base64,{content}"/>']
    for word in overlay['words']:
        role=word.get('role','context');color=COLORS.get(role,COLORS['context'])
        points=' '.join(f'{x},{y}' for x,y in word['polygon'])
        parts.append(f'<polygon points="{points}" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="{3 if role in ("target","source") else 1.3}"><title>{escape(str(word.get("label","")))}</title></polygon>')
        if labels:
            x,y=np.mean(word['polygon'],axis=0)
            parts.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="14" fill="#17262c" stroke="white" stroke-width="3" paint-order="stroke">{escape(str(word.get("label","")))}</text>')
    parts.append('</svg>');return ''.join(parts)


def export_overlay(prefix, folio, words, *, title='Manuscript word boxes', labels=False, **kwargs):
    """Write <prefix>.jpg, .json and a self-contained .svg; return overlay data."""
    image, data=image_overlay(folio,words,**kwargs)
    prefix=Path(prefix);prefix.parent.mkdir(parents=True,exist_ok=True)
    image.save(prefix.with_suffix('.jpg'),quality=90)
    data['image']=prefix.with_suffix('.jpg').name
    prefix.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    prefix.with_suffix('.svg').write_text(overlay_svg(image,data,title=title,labels=labels),encoding='utf-8')
    return data


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path,help='JSON object with folio and words')
    ap.add_argument('--out',required=True,type=Path,help='Output filename prefix')
    ap.add_argument('--source',choices=['beinecke','display'],default='beinecke')
    ap.add_argument('--labels',action='store_true');ap.add_argument('--max-width',type=int,default=1800)
    args=ap.parse_args();spec=json.loads(args.input.read_text(encoding='utf-8'))
    export_overlay(args.out,spec['folio'],spec['words'],warp=spec.get('warp'),source=args.source,labels=args.labels,max_width=args.max_width)


if __name__=='__main__':main()
