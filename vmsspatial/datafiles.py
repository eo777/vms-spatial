"""Fetch the data files listed in resources/data_manifest.json into the data folder, and verify them.

The manifest has two kinds of entry. Shipped files travel with the repository (the transcription, the word rectangles with
their alignment review, the control texts and streams); ``fetch-data`` refreshes them from their published copies.
Optional files are not in the repository: the inputs the review was built from (group ``raw``: the Voynichese XML pages,
the frozen page-wise alignment, the coordinate inventories), two files of the October 2026 studies (``model``: the
positional composition model; ``reference``: the component-impact table) and the full-resolution Beinecke scans
(``images``). Each is referenced by a published URL or by its path in the research workspace; the toolkit reads one when
it is present (``paths.resolve``) and never requires it, and ``publish.py`` never ships it.

    vmsspatial fetch-data                      # refresh the shipped files from their published copies
    vmsspatial fetch-data --group images       # one group, its optional files included: raw, model, reference, images
    vmsspatial fetch-data --optional           # every optional file that has a published copy
    vmsspatial fetch-data --from-workspace     # copy from the research workspace instead of downloading (VMS_WORKSPACE)
    vmsspatial verify-data                     # SHA-256 of every present file against the manifest
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

from . import paths


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def register(key: str, note: str, group: str = 'manuscript', license: str = None, workspace: str = None, log=print) -> dict:
    """Record a (re)built shipped data file in resources/data_manifest.json: its SHA-256 and size, its path in the
    research workspace (default: the toolkit's own data folder), no published URL until a release carries it. The
    manifest's version becomes today's date (with a counter for several builds a day). Returns the entry."""
    import json
    from datetime import date
    p = paths.data_dir() / key
    if not p.is_file():
        raise paths.DataMissing('%s is not in %s' % (key, paths.data_dir()))
    mpath = paths.RESOURCES / 'data_manifest.json'
    m = json.loads(mpath.read_text(encoding='utf-8'))
    entry = next((e for e in m['files'] if e['key'] == key), None)
    if entry is None:
        entry = dict(key=key, group=group, workspace=workspace or 'apps/spatial_toolkit/data/' + key, url=None, note=note, sha256='', bytes=0, optional=False)
        m['files'].append(entry)
    entry.update(sha256=sha256(p), bytes=p.stat().st_size, note=note or entry.get('note'), url=None, workspace=workspace or 'apps/spatial_toolkit/data/' + key)
    if license:
        entry['license'] = license
    today = date.today().isoformat()
    v = str(m.get('version') or '')
    if v == today or v.startswith(today + '.'):
        n = 1 if v == today else int(v.split('.')[-1])
        m['version'] = '%s.%d' % (today, n + 1)
    else:
        m['version'] = today
    mpath.write_text(json.dumps(m, indent=1) + '\n', encoding='utf-8')
    paths.manifest.cache_clear()
    paths.manifest_entry.cache_clear()
    if log:
        log('manifest %s: %s (%d bytes, sha256 %s...)' % (m['version'], key, entry['bytes'], entry['sha256'][:12]))
    return entry


def is_optional(entry: dict) -> bool:
    return bool(entry.get('optional'))


def selected(groups=None, optional=False):
    """The manifest entries a fetch covers: the shipped files, plus the optional ones when `optional` is set or their
    group is named."""
    for e in paths.manifest()['files']:
        if groups and e['group'] not in groups:
            continue
        if is_optional(e) and not optional and not groups:
            continue
        yield e


def fetch(groups=None, from_workspace=False, force=False, out=None, log=print, optional=False):
    """Returns (fetched, skipped, failed) lists of manifest keys."""
    target = Path(out) if out else paths.data_dir()
    ws = paths.workspace_dir() if from_workspace else None
    if from_workspace and ws is None:
        raise paths.DataMissing('no research workspace found (set VMS_WORKSPACE)')
    fetched, skipped, failed = [], [], []
    for e in selected(groups, optional):
        dest = target / e['key']
        if dest.is_file() and not force and sha256(dest) == e['sha256']:
            skipped.append(e['key'])
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if ws is not None and e.get('workspace'):
                shutil.copyfile(ws / e['workspace'], dest)
            elif e.get('url'):
                log('downloading %s' % e['key'])
                with urllib.request.urlopen(e['url'], timeout=120) as r, open(dest, 'wb') as f:
                    shutil.copyfileobj(r, f)
            else:
                failed.append(e['key'] + ' (no published copy; use --from-workspace)')
                continue
            if sha256(dest) != e['sha256']:
                failed.append(e['key'] + ' (SHA-256 differs from the manifest)')
                continue
            fetched.append(e['key'])
        except (OSError, urllib.error.URLError) as err:
            failed.append('%s (%s)' % (e['key'], err))
    return fetched, skipped, failed


def verify(groups=None) -> dict:
    """{ok, missing, bad, optional_missing}: lists of manifest keys. A missing optional file is not a defect."""
    out = dict(ok=[], missing=[], bad=[], optional_missing=[])
    for e in paths.manifest()['files']:
        if groups and e['group'] not in groups:
            continue
        p = paths.resolve(e['key'], required=False)
        if p is None:
            out['optional_missing' if is_optional(e) else 'missing'].append(e['key'])
        elif sha256(p) != e['sha256']:
            out['bad'].append(e['key'])
        else:
            out['ok'].append(e['key'])
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from-workspace', action='store_true')
    ap.add_argument('--group', action='append', help='manuscript, raw, controls, images, model, reference (repeatable; a named group includes its optional files)')
    ap.add_argument('--optional', action='store_true', help='include every optional file')
    ap.add_argument('--force', action='store_true', help='refetch files that are already present and correct')
    ap.add_argument('--out', help='data folder (default: VMS_SPATIAL_DATA or <toolkit>/data)')
    args = ap.parse_args(argv)
    fetched, skipped, failed = fetch(args.group, args.from_workspace, args.force, args.out, optional=args.optional)
    print('%d fetched, %d already present, %d failed' % (len(fetched), len(skipped), len(failed)))
    for f in failed:
        print('  failed: ' + f)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
