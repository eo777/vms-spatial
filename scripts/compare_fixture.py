"""Write viewer/test/fixtures/compare_pairs.json: 30 saved pairs with the Python results of vmsspatial.compare on
the atlas's compact comparison records, which viewer/test/compare_math.test.js recomputes in JavaScript and checks
to 1e-9. Run after `vmsspatial viewer-data`.

    python scripts/compare_fixture.py
"""
import json
import sys
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT))

from vmsspatial import compare as C                      # noqa: E402
from vmsspatial.bundle import read_json                  # noqa: E402

DATA = TOOLKIT / 'viewer' / 'data'
OUT = TOOLKIT / 'viewer' / 'test' / 'fixtures' / 'compare_pairs.json'

OVERLAY = [('f20v', 'f21r', 3, 'flat', 'starts', 'pixels', False), ('f20v', 'f10v', 3, 'flat', 'starts', 'pixels', False), ('f21r', 'f15r', 1, 'flat', 'starts', 'pixels', False),
           ('f47r', 'f56r', 5, 'recorded', 'starts', 'pixels', False), ('f47r', 'f56r', 5, 'recorded', 'starts', 'pixels', True), ('f56r', 'f7r', 2, 'flat', 'starts', 'body_height', False),
           ('f7r', 'f32r', 'all', 'flat', 'page', 'pixels', False), ('f7v', 'f22r', 1, 'flat', 'starts', 'pixels', False), ('f13r', 'f20v', 4, 'recorded', 'starts', 'pixels', False),
           ('f75r', 'f76r', 'all', 'flat', 'page', 'pixels', False), ('f104r', 'f115r', 1, 'flat', 'starts', 'pixels', False), ('f78v', 'f80v', 3, 'flat', 'starts', 'body_height', True),
           ('f1r', 'f8r', 'all', 'recorded', 'page', 'pixels', False), ('f30r', 'f37r', 2, 'flat', 'starts', 'pixels', False), ('f16r', 'f22r', 5, 'flat', 'page', 'pixels', False)]
BLOCKS = [('f7r', 'p2', 'f32r', 'p1', 'all', 'flat', 'starts'), ('f47r', 'p2', 'f56r', 'opening', 5, 'recorded', 'starts'), ('f75r', 'p3', 'f76r', 'p2', 3, 'flat', 'page'),
          ('f20v', 'p1', 'f21r', 'p1', 'all', 'flat', 'starts'), ('f68r2', 'page', 'f68r1', 'page', 'all', 'recorded', 'page')]
SCAN = [('f20v', 'f21r'), ('f13r', 'f20v'), ('f7v', 'f22r'), ('f7v', 'f21v'), ('f22r', 'f21v'), ('f104r', 'f115r'), ('f78v', 'f80v'), ('f1r', 'f1v'), ('f31v', 'f43v'), ('f28r', 'f54r')]


def main():
    compact = read_json(DATA / 'compare' / 'pages.json.gz')
    words = read_json(DATA / 'manuscript' / 'words.json.gz')['words']
    data = C.pages_from_viewer(compact, words)
    pairs = []
    for a, b, cutoff, coords, align, scale, same_row in OVERLAY:
        sa, sb = C.select(data, a, 'opening', cutoff, coords, align, scale), C.select(data, b, 'opening', cutoff, coords, align, scale)
        d = C.details(sa, sb, same_row)
        pairs.append(dict(kind='overlay', a=a, b=b, block_a='opening', block_b='opening', cutoff=cutoff, coordinates=coords, alignment=align, scale=scale, same_row=same_row,
                          expected=C.measure(sa, sb, same_row), details=dict(direct=len(d['direct']), connected=len(d['connected']), nearby=len(d['nearby']),
                                                                             connected_similarity=[round(c['similarity'], 12) for c in d['connected']]),
                          per_line=C.per_line(sa, sb) if cutoff != 'all' else None, selection=dict(a=dict(chosen=len(sa['chosen']), complete=sa['complete'], origin=sa['origin'], anchor_kind=sa['anchor_kind']),
                                                                                                    b=dict(chosen=len(sb['chosen']), complete=sb['complete'], origin=sb['origin']))))
    for a, ba, b, bb, cutoff, coords, align in BLOCKS:
        sa, sb = C.select(data, a, ba, cutoff, coords, align), C.select(data, b, bb, cutoff, coords, align)
        pairs.append(dict(kind='blocks', a=a, b=b, block_a=ba, block_b=bb, cutoff=cutoff, coordinates=coords, alignment=align, scale='pixels', same_row=False, expected=C.measure(sa, sb),
                          selection=dict(a=dict(chosen=len(sa['chosen']), complete=sa['complete'], origin=sa['origin'], available=sa['available']), b=dict(chosen=len(sb['chosen']), complete=sb['complete'], origin=sb['origin'], available=sb['available']))))
    scan = []
    for a, b in SCAN:
        cur = [C.select(data, f, 'opening', 1, 'flat', 'starts', 'pixels') for f in (a, b)]
        rec = [C.select(data, f, 'opening', 1, 'recorded', 'starts', 'pixels') for f in (a, b)]
        body = [C.select(data, f, 'opening', 1, 'flat', 'starts', 'body_height') for f in (a, b)]
        A, B = [u for u in cur[0]['chosen'] if not u['anchor']], [u for u in cur[1]['chosen'] if not u['anchor']]
        texts = [' '.join(data['pages'][f]['lines'][data['pages'][f]['blocks'][0]['lines'][0]]['text'].split()) for f in (a, b)]
        fa, fb = C.line_features(texts[0]), C.line_features(texts[1])
        scan.append(dict(a=a, b=b, text_a=texts[0], text_b=texts[1], expected=dict(
            spatial=C.spatial_similarity(A, B)['similarity'], x_dice=C.x_dice(A, B), dice_current=C.dice2d(A, B),
            dice_recorded=C.dice2d([u for u in rec[0]['chosen'] if not u['anchor']], [u for u in rec[1]['chosen'] if not u['anchor']]),
            spatial_body=C.spatial_similarity([u for u in body[0]['chosen'] if not u['anchor']], [u for u in body[1]['chosen'] if not u['anchor']])['similarity'],
            edit_all=C.similarity(fa['plain'], fb['plain']), js_word=C.js_distance(fa['toolkit'], fb['toolkit']), js_joined=C.js_distance(fa['joined'], fb['joined']),
            js_boundaries=C.js_distance(fa['boundaries'], fb['boundaries']))))
    rows = [dict(id='p:%d' % k, dice_current=v[0], js_joined=v[1]) for k, v in enumerate([(0.8, 0.5), (0.7, 0.4), (0.8, 0.6), (0.6, 0.4), (0.9, 0.9)])]
    ranked = C.rank_rows(rows)
    data['quarantine'] = compact.get('quarantine', [])
    drift = []
    for f in ('f21v', 'f112v', 'f20v', 'f75r', 'f86v3', 'f116v', 'f1r', 'f104r'):
        for coords in ('recorded', 'flat'):
            d = C.page_drift(data, f, coords)
            drift.append(dict(folio=f, coordinates=coords, quarantined=f in data['quarantine'], angle=d['angle'], slope=d['slope'], n=d['n'], lines=len(d['lines']), dropped=d['dropped'], unavailable=d['unavailable'],
                              line_angles=[[l['index'], l.get('angle'), l['qualifies']] for l in d['lines']], shipped=compact['pages'][f]['drift'][coords]))
    splits = []
    for a, b, idx in (('f21v', 'f15v', [0, 0]), ('f21v', 'f15v', [7, 11]), ('f20v', 'f21r', [2, 2])):
        sa, sb = C.select(data, a, 'page', 'all', 'flat', 'page'), C.select(data, b, 'page', 'all', 'flat', 'page')
        for scale in (0.12, 0.7):
            s = C.split_lines(sa, sb, idx, scale)
            splits.append(dict(a=a, b=b, indices=idx, scale=scale, start=s['start'], end=s['end'], row_tops=s['row_tops'], up=s['up'], down=s['down'], ymin=s['ymin'], ymax=s['ymax'],
                               first_rects=[s['selections'][k]['all'][0]['rect'] for k in (0, 1)], scores_unchanged=C.measure(sa, sb)))
    fixture = dict(note='Saved Python results of vmsspatial.compare on the compact atlas records (viewer/data/compare/pages.json.gz); compare_math.test.js recomputes them. Rebuild with scripts/compare_fixture.py.',
                   version=compact['version'], pages_file='compare/pages.json.gz', words_file='manuscript/words.json.gz', pairs=pairs, scan=scan, drift=drift, splits=splits,
                   ranking=dict(rows=rows, order=[r['id'] for r in ranked], both_worst=[r['both_worst'] for r in ranked], overlap=[r['overlap_rank'] for r in ranked], js=[r['js_rank'] for r in ranked]),
                   joint_example=C.joint([]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1), encoding='utf-8')
    print('wrote %s: %d overlay/block pairs, %d scan pairs (%d bytes)' % (OUT, len(pairs), len(scan), OUT.stat().st_size))


if __name__ == '__main__':
    main()
