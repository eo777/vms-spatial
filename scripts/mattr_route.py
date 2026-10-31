"""MATTR along the route: by Golf group and by bifolium, with the shuffled-bag expectation and the clustering gap, for
the manuscript and for any control; the late steps split into a bag part and a clustering part.

    python scripts/mattr_route.py
    python scripts/mattr_route.py --control markov:section
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial.manuscript import STUDY   # the 2026 studies: paragraph text, Path 1 order, recorded rectangles
from vmsspatial import Manuscript, load_bundle
from vmsspatial.measures import group_table
from vmsspatial.manuscript import group_labels
from vmsspatial.controls import build_control


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--control', action='append', help='kind:name, as for `vmsspatial control`')
    ap.add_argument('--window', type=int, default=100)
    args = ap.parse_args()
    ms = Manuscript.load(**STUDY)
    texts = {'manuscript': ms.line_words()}
    if args.control:
        app = load_bundle('sensitivity', warp='recorded', **STUDY)
        for spec in args.control:
            kind, _, name = spec.partition(':')
            texts[spec] = build_control(ms, app, kind, name or None)[0]     # (lines, geometry, components, info)
    groups = [g for g in ['1a', '1b', '1.5a', '2a', '5a', '6', '3b', '3a', '3c', '4c', '4a']]
    print('MATTR%d by Golf group (bag expectation in brackets); clustering gap = bag - actual' % args.window)
    print('%-28s ' % '' + ' '.join('%14s' % g for g in group_labels(groups, sep=' ')))
    for name, lines in texts.items():
        t = group_table(ms, lines, groups, args.window)
        print('%-28s ' % name + ' '.join('%6.3f [%5.3f]' % (t['groups'][g]['mattr'], t['groups'][g]['bag']) for g in groups))
        print('%-28s ' % '  steps' + '  '.join('%s: %+.3f = bag %+.3f + clustering %+.3f' % (k, v['actual'], v['bag'], v['clustering']) for k, v in t['steps'].items()))


if __name__ == '__main__':
    main()
