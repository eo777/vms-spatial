"""Lossless EVA/IVTFF token atomization shared by every transform."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

COMPOSITES: Tuple[str, ...] = ("cph", "cfh", "ckh", "cth", "ch", "sh")
_EXTENDED_RE = re.compile(r"@\d+;")
_BENCH_EXTENDED_RE = re.compile(r"^\{c@\d+;h\}$")


@dataclass(frozen=True)
class Atom:
    raw: str
    kind: str

    @property
    def is_extended(self) -> bool:
        return self.kind in ("extended", "bench_extended", "ligature")


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
            raw = word[i : j + 1]
            kind = "bench_extended" if _BENCH_EXTENDED_RE.match(raw) else "ligature"
            atoms.append(Atom(raw, kind))
            i = j + 1
            continue
        if word[i] == "@":
            match = _EXTENDED_RE.match(word, i)
            if match:
                atoms.append(Atom(match.group(0), "extended"))
                i = match.end()
                continue
        matched = False
        for composite in COMPOSITES:
            if word.startswith(composite, i):
                atoms.append(Atom(composite, "composite"))
                i += len(composite)
                matched = True
                break
        if matched:
            continue
        atoms.append(Atom(word[i], "glyph"))
        i += 1
    return tuple(atoms)


def render_eva(atoms: Iterable[Atom]) -> str:
    return "".join(atom.raw for atom in atoms)


def atom_strings(word: str) -> Tuple[str, ...]:
    return tuple(atom.raw for atom in parse_eva(word))


def replace_atoms(atoms: Sequence[Atom], replacements: Sequence[str]) -> str:
    """Render replacement strings; replacements may themselves contain EVA composites."""
    if len(atoms) != len(replacements):
        raise ValueError("replacement count must match atom count")
    return "".join(replacements)


def leading_atom(word: str) -> str:
    atoms = parse_eva(word)
    return atoms[0].raw if atoms else ""


def has_extended_atom(word: str) -> bool:
    return any(atom.is_extended for atom in parse_eva(word))
