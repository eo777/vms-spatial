"""Word positions for the Rosettes foldout: detect, link to the ZL loci, write the geometry supplement.

    python scripts/rosettes_geometry.py --image data/images/beinecke/fRos_1006231.jpg
        [--candidates cache.json] [--out data/manuscript/supplement_fRos.json] [--overlay review.jpg] [--display viewer/img/fRos.jpg]

The CRAFT detector (EasyOCR) runs once and is cached in --candidates; the ring segmentation and the label assignment
are pure numpy/OpenCV. See vmsspatial.rosettes and docs/ROSETTES.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vmsspatial import rosettes, paths  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True, help='the Beinecke IIIF image of the 85v/86r foldout (7925 x 7268)')
    ap.add_argument('--candidates', help='cache of detector candidates (JSON); created when missing')
    ap.add_argument('--out', default=str(paths.data_dir() / 'manuscript' / 'supplement_fRos.json'))
    ap.add_argument('--overlay', help='write a review image with every placed box')
    ap.add_argument('--display', help='write the quarter-scale display image (viewer/img/fRos.jpg)')
    args = ap.parse_args()
    layout = rosettes.load_layout()
    cache = args.candidates or str(Path(args.out).with_name('fRos_candidates.json'))
    rec = rosettes.build(args.image, layout, candidate_cache=cache)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rec, indent=0), encoding='utf-8')
    print('wrote', args.out)
    if args.overlay:
        rosettes.draw_overlay(args.image, rec, args.overlay, layout['image'].get('display_scale', 0.25))
        print('wrote', args.overlay)
    if args.display:
        rosettes.write_display_image(args.image, args.display, layout['image'].get('display_scale', 0.25))
        print('wrote', args.display)


if __name__ == '__main__':
    main()
