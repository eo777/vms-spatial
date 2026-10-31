"""Run the JavaScript reference scorer (js/measure_cli.js, the viewer's own selector and formulas) from Python.

Used by the parity tests and available for anyone who wants the viewer's numbers rather than the Python port's:

    from vmsspatial.jsref import js_score
    table = js_score(bundle)                      # study selector + reading-order windows, as the viewer computes them
    table = js_score(bundle, configs=[spec.as_dict() for spec in specs])   # sweep form
Needs `node` on the PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .paths import TOOLKIT

CLI = TOOLKIT / 'js' / 'measure_cli.js'


def node_available() -> bool:
    return shutil.which('node') is not None


def _arrays(obj):
    return {k: (np.array([np.nan if v is None else v for v in vals], dtype=float) if vals and not isinstance(vals[0], dict) else vals) for k, vals in obj.items()}


def js_score(bundle: dict, policy: str = 'strict', configs: Optional[List[dict]] = None) -> Dict[str, np.ndarray]:
    if not node_available():
        raise RuntimeError('node is not on the PATH')
    with tempfile.TemporaryDirectory() as td:
        pin, pout = Path(td) / 'in.json', Path(td) / 'out.json'
        pin.write_text(json.dumps(bundle), encoding='utf-8')
        cmd = ['node', str(CLI), str(pin), str(pout), '--policy', policy]
        if configs:
            pcfg = Path(td) / 'cfg.json'
            pcfg.write_text(json.dumps(configs), encoding='utf-8')
            cmd += ['--configs', str(pcfg)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        out = json.loads(pout.read_text(encoding='utf-8'))
    if configs:
        return {name: _arrays(block) for name, block in out.items()}
    return _arrays(out)
