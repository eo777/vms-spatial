"""Davis plain-p/f expansion (the one transform the lattice parser needs), vendored from voynich_toolkit.transforms."""
from __future__ import annotations

from typing import List

from .eva import parse_eva


def expand_plain_pf(word: str) -> tuple:
    """Return Davis plain-p/f expansion plus an atom-position trace."""
    replacements: List[str] = []
    trace: List[str] = []
    for position, atom in enumerate(parse_eva(word), start=1):
        if atom.kind == "glyph" and atom.raw == "p":
            replacements.append("ke")
            trace.append("p@%d->ke" % position)
        elif atom.kind == "glyph" and atom.raw == "f":
            replacements.append("te")
            trace.append("f@%d->te" % position)
        else:
            replacements.append(atom.raw)
    return "".join(replacements), tuple(trace)
