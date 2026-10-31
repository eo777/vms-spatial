"""Glyph units of a Voynich word (the components of the diversity measures).

Vendored from the research workspace's ``voynich_gradients.eva`` / ``glyph_units`` (lossless EVA atomization and the
Zattera slot alphabet) so that the toolkit stands alone. ``zattera(word)`` is the component function of every Voynich
text in this toolkit and of the heatmap viewer (``js/common.js`` ports the same rules); ``letters(word)`` is the
component function used for natural-language control texts.

Rules of the Zattera unitizer (Zattera 2022, section 2.2): benches ``ch``/``sh`` and pedestalled gallows
``cth``/``ckh``/``cph``/``cfh`` are one unit; maximal runs of ``e`` or ``i`` are one unit; extended ``@nnn;`` atoms,
``{...}`` ligatures and literals stay whole. ``''.join(zattera(w)) == w`` for every word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

COMPOSITES: Tuple[str, ...] = ("cph", "cfh", "ckh", "cth", "ch", "sh")
_EXTENDED_RE = re.compile(r"@\d+;")
_BENCH_EXTENDED_RE = re.compile(r"^\{c@\d+;h\}$")
_ZATTERA_SINGLE = frozenset("qsdoylrktpfamn")
_RUN_GLYPHS = ("e", "i")
_WHOLE_KINDS = frozenset(("extended", "bench_extended", "ligature", "literal"))


@dataclass(frozen=True)
class Atom:
    raw: str
    kind: str


def parse_eva(word: str) -> Tuple[Atom, ...]:
    """Parse one token without losing extended or ligature notation."""
    atoms: List[Atom] = []
    i = 0
    while i < len(word):
        if word[i] == "{":
            j = word.find("}", i + 1)
            if j < 0:
                atoms.append(Atom(word[i], "literal"))
                i += 1
                continue
            raw = word[i:j + 1]
            atoms.append(Atom(raw, "bench_extended" if _BENCH_EXTENDED_RE.match(raw) else "ligature"))
            i = j + 1
            continue
        if word[i] == "@":
            m = _EXTENDED_RE.match(word, i)
            if m:
                atoms.append(Atom(m.group(0), "extended"))
                i = m.end()
                continue
        for composite in COMPOSITES:
            if word.startswith(composite, i):
                atoms.append(Atom(composite, "composite"))
                i += len(composite)
                break
        else:
            atoms.append(Atom(word[i], "glyph"))
            i += 1
    return tuple(atoms)


def atom_strings(word: str) -> Tuple[str, ...]:
    return tuple(a.raw for a in parse_eva(word))


def zattera(word: str) -> List[str]:
    """The Zattera slot-alphabet units of a word, in order."""
    atoms = parse_eva(word)
    out: List[str] = []
    i = 0
    while i < len(atoms):
        atom = atoms[i]
        if atom.kind in _WHOLE_KINDS or atom.kind == "composite":
            out.append(atom.raw)
            i += 1
        elif atom.raw in _RUN_GLYPHS:
            j = i
            while j < len(atoms) and atoms[j].kind == "glyph" and atoms[j].raw == atom.raw:
                j += 1
            out.append(atom.raw * (j - i))
            i = j
        else:
            out.append(atom.raw)
            i += 1
    return out


def raw_units(word: str) -> List[str]:
    """Every plain EVA character as one unit; bracketed and extended atoms stay whole."""
    out: List[str] = []
    for atom in parse_eva(word):
        if atom.kind in _WHOLE_KINDS:
            out.append(atom.raw)
        else:
            out.extend(atom.raw)
    return out


def letters(word: str) -> List[str]:
    """Component function for natural-language texts: the letters of the word."""
    return list(word)


COMPONENT_FUNCTIONS = {'zattera': zattera, 'raw': raw_units, 'letters': letters}
COMPONENT_MODES = {'zattera': 'zattera; lossless; within-word pairs only', 'raw': 'raw EVA characters; within-word pairs only',
                   'letters': 'letters; letter pairs'}
