"""Build the standard control bundles and the viewer data that shows them beside the manuscript.

    python scripts/make_controls.py            # Markov chains (whole, Currier, section), Gart 1487 two ways, three copier streams; all typeset
    python scripts/make_controls.py --quick    # Markov section chain and one copier only
Then serve the toolkit folder (python -m http.server) and open viewer/index.html: the Text control lists every bundle.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial.viewer_data import build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--out')
    args = ap.parse_args()
    controls = ['markov:section', 'stream:timm_spatial'] if args.quick else [
        'markov:whole', 'markov:currier', 'markov:section', 'prose:de_gart_augsburg1487', 'prose_native:de_gart_augsburg1487', 'stream:timm', 'stream:timm_spatial', 'stream:noinnov_spatial']
    index = build(args.out, controls)          # the viewer's defaults: every page and locus, folio order, flat measures
    print('\n'.join('%-36s %s' % (b['key'], b['label']) for b in index['bundles']))


if __name__ == '__main__':
    main()
