"""Ink measurements: a synthetic word (known baseline, band, ascender, descender, 2 degree rotation) is recovered;
a synthetic two-line intrusion is detected; one real page is measured when its Beinecke scan is in the cache."""
import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from conftest import needs_data

from vmsspatial import ink
from vmsspatial.ink import measure_region, intrusions, gap_table, UNIT_FIELDS, LINE_FIELDS, UNCLEAN, flag_names

BASE, MEAN = 140.0, 100.0          # baseline and mean line of the synthetic word (rows, before rotation)
ASC_TOP, DESC_BOT = 60.0, 176.0    # ascender top and descender bottom
ROT = 2.0                          # PIL rotates counter-clockwise on screen: the word rises to the right
W, H = 420, 240
H_IMG = 90.0                       # the "page median box height" of the synthetic page (x-height 40 = 0.44 H)


def _word_image(seed=1):
    rng = np.random.default_rng(seed)
    bg = np.stack([np.full((H, W), 226.0), np.full((H, W), 212.0), np.full((H, W), 182.0)], -1)
    bg += rng.normal(0, 7, bg.shape)
    bg += np.linspace(-12, 12, W)[None, :, None]
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    inkc = (72, 48, 30)
    for k in range(6):
        x = 60 + 50 * k
        d.rectangle([x, MEAN, x + 34, BASE], outline=inkc, width=7)       # hollow letter bodies with flat tops and bottoms
    d.rectangle([160, ASC_TOP, 167, MEAN + 4], fill=inkc)              # the ascender
    d.rectangle([310, BASE - 4, 317, DESC_BOT], fill=inkc)             # the descender
    rot = im.rotate(ROT, resample=Image.BICUBIC, fillcolor=(226, 212, 182))
    return np.asarray(rot.convert('RGB'))


def _rotate_point(x, y):
    """Where PIL's rotate (counter-clockwise on screen, about the image centre) puts a point."""
    cx, cy = W / 2.0, H / 2.0
    t = math.radians(ROT)
    return cx + (x - cx) * math.cos(t) + (y - cy) * math.sin(t), cy - (x - cx) * math.sin(t) + (y - cy) * math.cos(t)


def test_synthetic_word_is_recovered():
    rgb = _word_image()
    gray = rgb.mean(-1)
    ys, xs = np.nonzero(gray < 140)
    box = [xs.min() - 3, ys.min() - 3, xs.max() + 4, ys.max() + 4]
    r = measure_region(rgb, box, H_IMG)
    assert r['base'] is not None, flag_names(r['flags'])
    assert not (r['flags'] & UNCLEAN), flag_names(r['flags'])
    # the expected angle: the rotated baseline's slope (positive = falls to the right). PIL's rectangle includes its
    # end rows, so the ink's lower edge is BASE + 1 (the edge below row BASE) and its upper edge MEAN
    (xa, ya), (xb, yb) = _rotate_point(60, BASE + 1), _rotate_point(345, BASE + 1)
    expected_angle = math.degrees(math.atan2(yb - ya, xb - xa))
    assert abs(r['angle_deg'] - expected_angle) < 0.5, (r['angle_deg'], expected_angle)
    # band edges at the measured centre, within 1 px
    xc = r['xc']
    base_at = ya + (yb - ya) * (xc - xa) / (xb - xa)
    (xm, ym), (xn, yn) = _rotate_point(60, MEAN), _rotate_point(345, MEAN)
    mean_at = ym + (yn - ym) * (xc - xm) / (xn - xm)
    assert abs(r['base'] - base_at) < 1.0, (r['base'], base_at)
    assert abs(r['mean'] - mean_at) < 1.0, (r['mean'], mean_at)
    assert abs(r['xheight'] - (BASE + 1 - MEAN)) < 1.5
    # ascender and descender found at the right places (within 2 px), with their x positions
    assert r['asc'] is not None and r['desc'] is not None
    ax, ay = _rotate_point(164.0, ASC_TOP + 0.5)                       # pixel centres of the extreme ink pixels
    dx, dy = _rotate_point(314.0, DESC_BOT + 0.5)
    assert abs(r['asc'][0] - ay) < 2.5 and abs(r['asc'][1] - ax) < 6, (r['asc'], (ay, ax))
    assert abs(r['desc'][0] - dy) < 2.5 and abs(r['desc'][1] - dx) < 6, (r['desc'], (dy, dx))
    # the ink's extent covers the six rings
    (x0, _), (x1, _) = _rotate_point(60, BASE), _rotate_point(345, BASE)
    assert abs(r['x0'] - x0) < 4 and abs(r['x1'] - x1) < 4
    # forcing the angle gives the same band
    r2 = measure_region(rgb, box, H_IMG, angle_deg=expected_angle)
    assert abs(r2['base'] - r['base']) < 0.7 and r2['flags'] & ink.ANGLE_FALLBACK == 0


def _toy_product(ms, app, upper, lower):
    """An ink product with hand-made records for two lines (dicts of UNIT_FIELDS per rectangle)."""
    from vmsspatial.bundle import digest
    prod = dict(version='test', words_sha256=digest(app['words']), geometry_sha256=digest(app['geometry']), residual_var_H2=0.01,
                units={f: [] for f in UNIT_FIELDS}, lines={f: [] for f in LINE_FIELDS}, pages={}, flags={})
    for rec in upper + lower:
        for f in UNIT_FIELDS:
            prod['units'][f].append(rec.get(f))
    for l, recs in ((0, upper), (1, lower)):
        xs = np.array([r['xc'] for r in recs]); ys = np.array([r['base'] for r in recs])
        c = np.polyfit(xs, ys, 1)
        L = dict(line=l, n_units=len(recs), n_clean=len(recs), angle=math.degrees(math.atan(c[0])), intercept=float(np.polyval(c, xs.mean())), x_mid=float(xs.mean()),
                 resid_rms=0.0, xheight_med=float(np.median([r['xheight'] for r in recs])), xheight_mad=0.0, box_ls_angle=0.0, box_chord_angle=0.0,
                 shift_dx=0.0, shift_dy=0.0, shift_n=0, ink_dx=0.0, ink_dy=0.0, ink_z=0.0)
        for f in LINE_FIELDS:
            prod['lines'][f].append(L[f])
    return prod


def test_synthetic_intrusion_is_detected():
    # two lines of one paragraph on a page with H = 30: the upper line's second word has a descender reaching 4 px
    # below the lower line's mean line; the lower line's third word has an ascender reaching above the upper baseline
    words = ['aa', 'by', 'cc', 'dd', 'ee', 'kf', 'gg']
    geometry = [[100, 100, 160, 130], [180, 100, 240, 145], [260, 100, 320, 130],
                [100, 150, 160, 180], [180, 150, 240, 180], [260, 135, 320, 180], [340, 150, 400, 180]]
    lines = [dict(page='f1r', locus='1', start=0, end=3), dict(page='f1r', locus='2', start=3, end=7)]
    app = dict(words=words, lines=lines, geometry=[[float(v) for v in g] for g in geometry], components={w: [w] for w in words}, component_mode='raw', geometry_kind='recorded')
    ms = dict(lines=[dict(page=0, chars=6, folio='f1r', locus='1', first=True), dict(page=0, chars=8, folio='f1r', locus='2', first=False)],
              pages=[dict(index=0, folio='f1r', side='r', start_line=0, end_line=2, section_name='Test', hand='1')])

    def rec(first, line, box, base, xh, desc=None, asc=None):
        return dict(first=first, last=first, line=line, box_bottom=box[3], x0=box[0] + 2, x1=box[2] - 2, xc=(box[0] + box[2]) / 2, base=base, mean=base - xh,
                    asc_y=asc[0] if asc else None, asc_x=asc[1] if asc else None, desc_y=desc[0] if desc else None, desc_x=desc[1] if desc else None,
                    angle=0.0, xheight=xh, coverage=0.5, n_ink=500, flags=0)
    upper = [rec(0, 0, geometry[0], 128.0, 16.0), rec(1, 0, geometry[1], 128.0, 16.0, desc=(168.0, 230.0)), rec(2, 0, geometry[2], 128.0, 16.0)]
    lower = [rec(3, 1, geometry[3], 178.0, 16.0), rec(4, 1, geometry[4], 178.0, 14.0), rec(5, 1, geometry[5], 178.0, 16.0, asc=(126.0, 270.0)), rec(6, 1, geometry[6], 178.0, 16.0)]
    prod = _toy_product(ms, app, upper, lower)
    ev = intrusions(app, ms, prod, margin_H=0.05)
    down = [e for e in ev if e['direction'] == 'down']
    up = [e for e in ev if e['direction'] == 'up']
    assert len(down) == 1 and down[0]['upper_word'] == 'by' and down[0]['lower_word'] == 'ee'
    # the lower LINE's mean line is its fitted baseline 178 minus its median x-height 16 = 162 (the word's own band,
    # 164, is not used to select events); the descender reaches 168: depth 6 px = 0.2 H, against the word 4 px
    assert abs(down[0]['depth_H'] - 6.0 / 30.0) < 1e-6 and abs(down[0]['depth_word_H'] - 4.0 / 30.0) < 1e-6
    assert abs(down[0]['gap_H'] - (162.0 - 128.0) / 30.0) < 1e-6
    assert down[0]['lower_xh_rel_H'] is not None and down[0]['lower_xh_rel_H'] < 0        # the word under the intrusion is shorter than its line's median
    assert len(up) == 1 and up[0]['lower_word'] == 'kf' and up[0]['upper_word'] == 'cc' and abs(up[0]['depth_H'] - 2.0 / 30.0) < 1e-6
    rows = gap_table(app, ms, prod, ev)
    assert len(rows) == 4 and sum(r['under_descender'] for r in rows) == 1
    under = next(r for r in rows if r['under_descender'])
    assert under['word'] == 'ee' and abs(under['intrusion_depth_H'] - 6.0 / 30.0) < 1e-6 and abs(under['gap_H'] - (162.0 - 128.0) / 30.0) < 1e-6
    assert abs(under['gap_word_H'] - (164.0 - 128.0) / 30.0) < 1e-6
    assert all(r['intrusion_depth_H'] is None for r in rows if not r['under_descender'])


def _cached_f75r():
    from vmsspatial import images
    try:
        rec = images.registrations('beinecke').get('f75r')
        return bool(rec and rec.get('ok') and images.image_path('f75r', 'beinecke', rec.get('image_id')).is_file())
    except Exception:
        return False


@needs_data
@pytest.mark.skipif(not _cached_f75r(), reason='the Beinecke scan of f75r is not in the image cache')
def test_real_page_line(ms, sensitivity_recorded):
    sensitivity = sensitivity_recorded                             # the scan is registered to the recorded rectangles
    from vmsspatial.images import registration, page_image, Mapping
    from vmsspatial.geometry import line_units
    rec = registration('f75r', 'beinecke', sensitivity, ms)
    assert rec['ok'] and rec['n_inliers'] > 200 and rec['residual_px'] < 2.0
    img = page_image('f75r', 'beinecke', rec['image_id'])
    units = line_units(sensitivity, ms)
    page = ms.page('f75r')
    l = next(l for l in range(page['start_line'], page['end_line']) if len(units[l]) >= 6)
    H = float(np.median([u['box'][3] - u['box'][1] for k in range(page['start_line'], page['end_line']) for u in units[k]]))
    records, line = ink.measure_line(img, Mapping(rec, l), units[l], H)
    clean = [r for r in records if r['base'] is not None and not (r['flags'] & UNCLEAN)]
    assert len(clean) >= 0.5 * len(records), [flag_names(r['flags']) for r in records]
    for r in clean:
        assert r['box'][1] - 0.3 * H <= r['base'] <= r['box'][3] + 0.3 * H          # the baseline lies inside the box
        assert 0.25 * H <= r['xheight'] <= 0.85 * H
        assert r['x0'] >= r['box'][0] - 0.3 * H and r['x1'] <= r['box'][2] + 0.3 * H
    assert line['angle'] is not None and abs(line['angle']) < 6 and line['xheight_med'] > 0
