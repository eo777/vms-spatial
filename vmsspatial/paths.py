"""Where the toolkit finds its data.

The data files (the manuscript transcription, the word rectangles with their alignment review, the control texts) live
in a data folder, by default ``<toolkit>/data``, which the repository ships; ``vmsspatial fetch-data`` refreshes it or
downloads the optional files, and ``vmsspatial fetch-data --from-workspace`` copies from the research workspace. Override
the folder with the environment variable ``VMS_SPATIAL_DATA``. When a file is missing from the data folder and the
research workspace is reachable (``VMS_WORKSPACE`` or the toolkit's grandparent folder), the workspace copy is used.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
TOOLKIT = PACKAGE.parent
RESOURCES = PACKAGE / 'resources'


class DataMissing(FileNotFoundError):
    pass


def data_dir() -> Path:
    env = os.environ.get('VMS_SPATIAL_DATA')
    return Path(env).expanduser().resolve() if env else TOOLKIT / 'data'


def workspace_dir():
    """The research workspace, if one is reachable (it holds the original copies of every data file)."""
    env = os.environ.get('VMS_WORKSPACE')
    candidates = [Path(env).expanduser()] if env else []
    candidates.append(TOOLKIT.parents[1] if len(TOOLKIT.parents) > 1 else TOOLKIT.parent)
    for c in candidates:
        if (c / 'voynich_toolkit').is_dir() and (c / 'ZL_ivtff_raw.txt').is_file():
            return c.resolve()
    return None


@lru_cache(maxsize=None)
def manifest() -> dict:
    return json.loads((RESOURCES / 'data_manifest.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=None)
def manifest_entry(key: str):
    for e in manifest()['files']:
        if e['key'] == key:
            return e
    return None


def resolve(key: str, required: bool = True):
    """The path of a data file named by its manifest key (``manuscript/words.json.gz``), from the data folder or the
    workspace. Raises DataMissing with the command that fetches it."""
    p = data_dir() / key
    if p.is_file():
        return p
    entry = manifest_entry(key)
    ws = workspace_dir()
    if entry and ws and (ws / entry['workspace']).is_file():
        return ws / entry['workspace']
    if not required:
        return None
    if entry is None:
        raise DataMissing('%s is not in %s and not in the manifest' % (key, data_dir()))
    if entry.get('url'):
        hint = 'run: vmsspatial fetch-data --group %s' % entry['group']
    elif entry.get('optional'):
        hint = 'run: vmsspatial fetch-data --from-workspace --group %s (set VMS_WORKSPACE)' % entry['group']
    else:
        hint = 'the repository carries this file: install from a clone with pip install -e ., or set VMS_SPATIAL_DATA to its data folder'
    kind = 'an optional file, ' if entry.get('optional') else ''
    raise DataMissing('%s is %snot in %s (%s)' % (key, kind, data_dir(), hint))


def resource(name: str) -> Path:
    return RESOURCES / name
