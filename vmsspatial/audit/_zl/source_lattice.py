"""Versioned, uncertainty-preserving source lattice for ZL IVTFF 2.0.

This is the additive corpus-infrastructure layer promoted from the
TRANSLITERATION_PARITY workstream (TP0-TP6). It never overwrites the canonical
raw source; it parses ``ZL_ivtff_raw.txt`` into a structure that

* round-trips to the exact original bytes,
* tags every element with its ``(start, end)`` span into the raw line, and
* emits **explicit typed boundary edges** between adjacent token candidates.

Boundary semantics follow IVTFF 2.0.2 section 6.7 and are kept strictly
distinct:

======================  ======  ============================================
BoundaryType            symbol  meaning
======================  ======  ============================================
CERTAIN                 ``.``   certain apparent word space
UNCERTAIN               ``,``   uncertain apparent word space
INTRUSION_ALIGNED       ``<->`` drawing intrusion; a certain word space
INTRUSION_MISALIGNED    ``<~>`` poorly-aligned intrusion; a certain word space
======================  ======  ============================================

Intrusions are **never** merged and **never** relabelled as an ordinary space:
``airody<->chedaly`` is two tokens joined by an ``intrusion_aligned`` edge.

Two tokenization operations are supported separately:

* :func:`tokenize_all_spaces` - the canonical view; splits on all four
  boundary types and keeps every edge typed.
* :func:`tokenize_certain_spaces` - a sensitivity that merges commas
  (``UNCERTAIN``) into the surrounding token while still splitting on
  ``CERTAIN`` and both intrusions.

Named adjacency policies filter the typed edges for a consumer:

* ``certain_ordinary_only`` - edges of type CERTAIN
* ``ordinary_all`` - CERTAIN + UNCERTAIN (``.`` plus ``,``)
* ``include_intrusion`` - the above plus both intrusion edges (a separate
  sensitivity)

Reading/view sensitivities (``preferred_first`` is canonical; the rest are
never silently folded in): ``preferred_first``, ``certain_spaces``,
``alternatives_preserved``, ``conservative_q``, ``davis_pf``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from .pf import expand_plain_pf

SOURCE_LATTICE_VERSION = "1.0.0"
SOURCE_VERSION = "ZL3b-2025-05-13"
SOURCE_SHA256 = "bf5b6d4ac1e3a51b1847a9c388318d609020441ccd56984c901c32b09beccafc"

# Pinned raw-source census (IVTFF 2.0 ZL 3b). Any drift hard-fails at load.
PINNED = {
    "locus_lines": 5385,
    "boundary_certain": 30129,
    "boundary_uncertain": 2748,
    "boundary_intrusion_aligned": 758,
    "boundary_intrusion_misaligned": 6,
    "alt_groups": 817,
    "all_spaces_tokens": 39026,
}


# --------------------------------------------------------------------------
# Boundary types
# --------------------------------------------------------------------------
class BoundaryType:
    CERTAIN = "certain"
    UNCERTAIN = "uncertain"
    INTRUSION_ALIGNED = "intrusion_aligned"
    INTRUSION_MISALIGNED = "intrusion_misaligned"

    ALL: Tuple[str, ...] = (CERTAIN, UNCERTAIN, INTRUSION_ALIGNED, INTRUSION_MISALIGNED)
    INTRUSIONS: FrozenSet[str] = frozenset((INTRUSION_ALIGNED, INTRUSION_MISALIGNED))


_BOUNDARY_SYMBOL = {
    ".": BoundaryType.CERTAIN,
    ",": BoundaryType.UNCERTAIN,
    "<->": BoundaryType.INTRUSION_ALIGNED,
    "<~>": BoundaryType.INTRUSION_MISALIGNED,
}
_SYMBOL_FOR = {v: k for k, v in _BOUNDARY_SYMBOL.items()}


# Named adjacency policies (edge-type filters over an all-spaces tokenization).
ADJACENCY_POLICIES: Dict[str, FrozenSet[str]] = {
    "certain_ordinary_only": frozenset((BoundaryType.CERTAIN,)),
    "ordinary_all": frozenset((BoundaryType.CERTAIN, BoundaryType.UNCERTAIN)),
    "include_intrusion": frozenset(BoundaryType.ALL),
}

# Split-type sets for the two tokenization operations.
_ALL_SPACES_SPLIT = frozenset(BoundaryType.ALL)
_CERTAIN_SPACES_SPLIT = frozenset(
    (BoundaryType.CERTAIN, BoundaryType.INTRUSION_ALIGNED, BoundaryType.INTRUSION_MISALIGNED)
)

# Reading/view sensitivities. Only preferred_first is canonical.
READING_POLICIES: Tuple[str, ...] = (
    "preferred_first",       # canonical: first alternative reading
    "alternatives_preserved",  # keep [a:b] group verbatim
    "conservative_q",        # alternative group -> '?'
)
CANONICAL_READING = "preferred_first"


# --------------------------------------------------------------------------
# Parsed structure
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Element:
    """One span-tracked unit of a locus text; ``value`` is verbatim raw text."""

    kind: str      # atom | ligature | highascii | alt | boundary | comment | text_tag
    value: object  # str, list[str] (alt), BoundaryType (boundary), (var, val) (text_tag)
    start: int
    end: int


def effective_vars(page_vars: Mapping[str, str],
                   active_tags: Mapping[str, str]) -> Dict[str, str]:
    """Resolve effective page/text-tag variables (IVTFF 2.0 sec 6.8).

    A page variable value of ``@`` means the variable is controlled by
    ``<@X=y>`` text tags; the effective value is then the currently active tag
    value (empty until a tag has fired). Any other page value is constant
    across the page.
    """
    out: Dict[str, str] = {}
    for key in set(page_vars) | set(active_tags):
        pv = page_vars.get(key, "")
        out[key] = active_tags.get(key, "") if pv == "@" else pv
    return out


@dataclass(frozen=True)
class SourceLocus:
    page: str
    num: str
    locator: str          # @ + * = & ~ /  (the "prefix" column in tokens3)
    locus_type: str       # e.g. P0, Lz, Cc
    source_line_no: int
    raw_line: str
    tag_end: int
    elements: Tuple[Element, ...]
    page_vars: Mapping[str, str]
    entry_tags: Mapping[str, str] = field(default_factory=dict)  # text-tag state at locus start

    @property
    def category(self) -> str:
        return {"P": "para", "L": "label", "C": "circle", "R": "radial"}.get(
            self.locus_type[0], "other"
        )

    @property
    def locus_id(self) -> str:
        return "%s.%s" % (self.page, self.num)


@dataclass(frozen=True)
class Token:
    """A tokenization candidate with stable provenance and retained alternatives.

    Identity (:attr:`token_id`) is source-span based -- ``page.num@start:end`` --
    so it is stable across tokenization views: a certain-spaces merged token and
    an all-spaces token can never share an id unless they cover exactly the same
    raw characters (in which case they are the same token). ``index_in_locus`` is
    retained separately but is view-relative and must not be used for identity.
    """

    text: str
    page: str
    num: str
    locus_type: str
    locator: str
    category: str
    index_in_locus: int
    span_start: int
    span_end: int
    alternatives: Tuple[Tuple[str, ...], ...] = ()   # each [a:b] group, verbatim
    merged_interior: Tuple[str, ...] = ()            # boundary types merged inside
    has_alt: bool = False
    has_extended: bool = False
    has_ligature: bool = False
    has_unreadable: bool = False
    effective_vars: Tuple[Tuple[str, str], ...] = ()  # effective page/text-tag vars here

    @property
    def token_id(self) -> str:
        return "%s.%s@%d:%d" % (self.page, self.num, self.span_start, self.span_end)

    @property
    def source_span(self) -> Tuple[int, int]:
        return (self.span_start, self.span_end)

    def effective(self, name: str, default: str = "") -> str:
        for key, value in self.effective_vars:
            if key == name:
                return value
        return default


@dataclass(frozen=True)
class BoundaryEdge:
    """Typed edge connecting two adjacent tokens of the same locus.

    Endpoints are exposed both as view-relative indices (for in-memory token
    lookup) and as the published source-span token ids (:attr:`left_token_id` /
    :attr:`right_token_id`), which are what appears in tokens4/edges output.
    """

    boundary_type: str
    symbol: str
    span_start: int
    span_end: int
    page: str
    num: str
    left_index: int
    right_index: int
    left_token_id: str = ""
    right_token_id: str = ""

    @property
    def source_span(self) -> Tuple[int, int]:
        return (self.span_start, self.span_end)


@dataclass(frozen=True)
class LocusTokenization:
    locus: SourceLocus
    reading_policy: str
    operation: str                    # 'all_spaces' | 'certain_spaces'
    tokens: Tuple[Token, ...]
    edges: Tuple[BoundaryEdge, ...]

    def adjacency_pairs(self, policy: str) -> Tuple[Tuple[Token, BoundaryEdge, Token], ...]:
        """Return (left, edge, right) triples whose edge type is in ``policy``."""
        keep = _resolve_policy(policy)
        return tuple(
            (self.tokens[e.left_index], e, self.tokens[e.right_index])
            for e in self.edges
            if e.boundary_type in keep
        )


def _resolve_policy(policy) -> FrozenSet[str]:
    if isinstance(policy, (set, frozenset)):
        return frozenset(policy)
    try:
        return ADJACENCY_POLICIES[policy]
    except KeyError:
        raise KeyError(
            "Unknown adjacency policy %r; choose from %s or pass a set of BoundaryType"
            % (policy, sorted(ADJACENCY_POLICIES))
        )


# --------------------------------------------------------------------------
# IVTFF line parsing (span-tracked)
# --------------------------------------------------------------------------
_LOCUS_PREFIX_LEN = None  # computed per line


def _parse_text(line: str, tag_end: int) -> Tuple[Element, ...]:
    els: List[Element] = []
    i = tag_end
    n = len(line)
    atom_start = None

    def flush(upto: int) -> None:
        nonlocal atom_start
        if atom_start is not None:
            els.append(Element("atom", line[atom_start:upto], atom_start, upto))
            atom_start = None

    while i < n:
        c = line[i]
        if c == "<":
            flush(i)
            j = line.index(">", i) + 1
            body = line[i:j]
            if body in _BOUNDARY_SYMBOL:
                els.append(Element("boundary", _BOUNDARY_SYMBOL[body], i, j))
            elif body == "<%>":
                els.append(Element("par_start", body, i, j))
            elif body == "<$>":
                els.append(Element("par_end", body, i, j))
            elif len(body) > 3 and body[1] == "@" and "=" in body:
                # IVTFF text tag <@X=y> (sec 6.8): typed, not a comment
                var, _, val = body[2:-1].partition("=")
                els.append(Element("text_tag", (var, val), i, j))
            else:
                els.append(Element("comment", body, i, j))
            i = j
        elif c in ".,":
            flush(i)
            els.append(Element("boundary", _BOUNDARY_SYMBOL[c], i, i + 1))
            i += 1
        elif c == "[":
            flush(i)
            j = line.index("]", i) + 1
            els.append(Element("alt", tuple(line[i + 1:j - 1].split(":")), i, j))
            i = j
        elif c == "{":
            flush(i)
            j = line.index("}", i) + 1
            els.append(Element("ligature", line[i:j], i, j))
            i = j
        elif c == "@":
            flush(i)
            j = line.index(";", i) + 1
            els.append(Element("highascii", line[i:j], i, j))
            i = j
        elif c in " \t":
            flush(i)
            els.append(Element("white", c, i, i + 1))
            i += 1
        else:
            if atom_start is None:
                atom_start = i
            i += 1
    flush(n)
    return tuple(els)


def _serialize(elements: Sequence[Element]) -> str:
    out: List[str] = []
    for e in elements:
        if e.kind in ("atom", "white", "ligature", "highascii", "comment"):
            out.append(e.value)
        elif e.kind == "boundary":
            out.append(_SYMBOL_FOR[e.value])
        elif e.kind == "alt":
            out.append("[" + ":".join(e.value) + "]")
        elif e.kind == "text_tag":
            out.append("<@" + e.value[0] + "=" + e.value[1] + ">")
        elif e.kind == "par_start":
            out.append("<%>")
        elif e.kind == "par_end":
            out.append("<$>")
    return "".join(out)


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
import re as _re

_LOCUS_TAG_RE = _re.compile(r"^<(f[^>.]*)\.([^>,]+),(.)(..)>")
_PAGE_TAG_RE = _re.compile(r"^<([^>.,;]+)>")


class SourceLattice:
    """Parsed ZL document: round-trips exactly; span- and provenance-tracked."""

    def __init__(self, path, verify: bool = True):
        self.path = Path(path)
        with open(self.path, "r", encoding="ascii", newline="") as fh:
            self.raw = fh.read()
        self._init_from_raw(self.raw, verify)

    @classmethod
    def from_text(cls, raw: str, path: str = "<memory>", verify: bool = False) -> "SourceLattice":
        """Parse an arbitrary IVTFF string (e.g. a synthetic fixture) without the
        pinned full-corpus census gate. ``verify`` defaults to False because the
        pinned counts describe the real ZL source only."""
        obj = cls.__new__(cls)
        obj.path = Path(path)
        obj._init_from_raw(raw, verify)
        return obj

    def _init_from_raw(self, raw: str, verify: bool) -> None:
        self.raw = raw
        self._lines = raw.split("\n")
        if self._lines and self._lines[-1] == "":
            self._lines.pop()
        self.page_vars = {}
        self.loci = []
        self._parse()
        if verify:
            self.verify()

    def _parse(self) -> None:
        text_tags: Dict[str, str] = {}   # running text-tag state; resets per page
        current_page: Optional[str] = None
        for lineno, line in enumerate(self._lines, 1):
            if line.startswith("#"):
                continue
            m = _LOCUS_TAG_RE.match(line)
            if m:
                page, num, locator, ltype = m.groups()
                if page != current_page:
                    # a locus may open a page whose header we already read; the
                    # page boundary resets text-tag state (IVTFF 2.0 sec 6.8)
                    text_tags = {}
                    current_page = page
                page_vars = self.page_vars.get(page, {})
                elements = _parse_text(line, m.end())
                entry_tags = dict(text_tags)         # snapshot before this locus's tags
                # advance running state with any text tags in this locus so the
                # NEXT locus inherits them; only honoured where the page header
                # declares the variable text-tag-controlled ($X=@)
                for e in elements:
                    if e.kind == "text_tag":
                        var, val = e.value
                        if page_vars.get(var) == "@":
                            if val == "@":
                                text_tags.pop(var, None)
                            else:
                                text_tags[var] = val
                self.loci.append(SourceLocus(
                    page=page, num=num, locator=locator, locus_type=ltype,
                    source_line_no=lineno, raw_line=line, tag_end=m.end(),
                    elements=elements, page_vars=page_vars, entry_tags=entry_tags,
                ))
                continue
            pm = _PAGE_TAG_RE.match(line)
            if pm:
                # values are single chars; '@' means "text-tag controlled"
                self.page_vars[pm.group(1)] = dict(_re.findall(r"\$(\w)=([\w@])", line))
                text_tags = {}
                current_page = pm.group(1)

    # ---- exact round trip -------------------------------------------------
    def roundtrip(self) -> str:
        rebuilt = list(self._lines)
        for loc in self.loci:
            rebuilt[loc.source_line_no - 1] = loc.raw_line[:loc.tag_end] + _serialize(loc.elements)
        return "\n".join(rebuilt) + ("\n" if self.raw.endswith("\n") else "")

    # ---- census -----------------------------------------------------------
    def boundary_counts(self) -> Dict[str, int]:
        counts = {b: 0 for b in BoundaryType.ALL}
        for loc in self.loci:
            for e in loc.elements:
                if e.kind == "boundary":
                    counts[e.value] += 1
        return counts

    def alt_group_count(self) -> int:
        return sum(1 for loc in self.loci for e in loc.elements if e.kind == "alt")

    def verify(self) -> None:
        """Hard parity gate run at load; raises on any drift from the pinned census."""
        loaded_sha = hashlib.sha256(self.raw.encode("ascii")).hexdigest()
        if loaded_sha != SOURCE_SHA256:
            raise AssertionError(
                "source_lattice: loaded source SHA-256 %s != pinned %s"
                % (loaded_sha, SOURCE_SHA256))
        if self.roundtrip() != self.raw:
            raise AssertionError("source_lattice: raw round-trip is not byte-identical")
        bc = self.boundary_counts()
        checks = {
            "locus_lines": len(self.loci),
            "boundary_certain": bc[BoundaryType.CERTAIN],
            "boundary_uncertain": bc[BoundaryType.UNCERTAIN],
            "boundary_intrusion_aligned": bc[BoundaryType.INTRUSION_ALIGNED],
            "boundary_intrusion_misaligned": bc[BoundaryType.INTRUSION_MISALIGNED],
            "alt_groups": self.alt_group_count(),
        }
        for key, got in checks.items():
            if got != PINNED[key]:
                raise AssertionError(
                    "source_lattice parity gate failed: %s got %d, pinned %d"
                    % (key, got, PINNED[key]))
        # canonical (preferred-first / all-spaces) token total is a load-time gate
        n_canon = sum(len(lt.tokens) for lt in self.stream("all_spaces", CANONICAL_READING))
        if n_canon != PINNED["all_spaces_tokens"]:
            raise AssertionError(
                "source_lattice parity gate failed: canonical tokens got %d, pinned %d"
                % (n_canon, PINNED["all_spaces_tokens"]))

    # ---- tokenization -----------------------------------------------------
    def tokenize(self, locus: SourceLocus, operation: str = "all_spaces",
                 reading_policy: str = CANONICAL_READING) -> LocusTokenization:
        return _tokenize(locus, operation, reading_policy)

    def stream(self, operation: str = "all_spaces",
               reading_policy: str = CANONICAL_READING):
        for loc in self.loci:
            yield _tokenize(loc, operation, reading_policy)

    def all_tokens(self, operation: str = "all_spaces",
                   reading_policy: str = CANONICAL_READING) -> List[Token]:
        out: List[Token] = []
        for lt in self.stream(operation, reading_policy):
            out.extend(lt.tokens)
        return out


# --------------------------------------------------------------------------
# Core tokenizer (produces tokens + typed edges)
# --------------------------------------------------------------------------
def _render(element: Element, reading_policy: str) -> str:
    kind = element.kind
    if kind == "atom" or kind == "ligature" or kind == "highascii":
        return element.value
    if kind == "alt":
        if reading_policy == "preferred_first":
            return element.value[0]
        if reading_policy == "conservative_q":
            return "?"
        if reading_policy == "alternatives_preserved":
            return "[" + ":".join(element.value) + "]"
        raise KeyError("Unknown reading policy %r" % reading_policy)
    return ""


def _tokenize(locus: SourceLocus, operation: str, reading_policy: str) -> LocusTokenization:
    if operation == "all_spaces":
        split_types = _ALL_SPACES_SPLIT
    elif operation == "certain_spaces":
        split_types = _CERTAIN_SPACES_SPLIT
    else:
        raise KeyError("Unknown operation %r (all_spaces|certain_spaces)" % operation)

    tokens: List[Token] = []
    edges: List[BoundaryEdge] = []
    prev_index: Optional[int] = None
    pending: Optional[Tuple[str, int, int]] = None   # (btype, start, end)
    active_tags: Dict[str, str] = dict(locus.entry_tags)  # text-tag state carried in

    parts: List[str] = []
    alts: List[Tuple[str, ...]] = []
    merged: List[str] = []
    span0: Optional[int] = None
    span1: Optional[int] = None
    tok_tags: Dict[str, str] = {}    # snapshot of active_tags at token start
    has_ext = has_lig = has_unr = False

    def reset() -> None:
        nonlocal parts, alts, merged, span0, span1, has_ext, has_lig, has_unr
        parts, alts, merged = [], [], []
        span0 = span1 = None
        has_ext = has_lig = has_unr = False

    def finish() -> None:
        nonlocal prev_index, pending
        text = "".join(parts)
        if text == "":
            reset()
            return
        index = len(tokens)
        right_id = "%s.%s@%d:%d" % (locus.page, locus.num, span0, span1)
        if pending is not None and prev_index is not None:
            btype, bs, be = pending
            edges.append(BoundaryEdge(
                boundary_type=btype, symbol=_SYMBOL_FOR[btype],
                span_start=bs, span_end=be, page=locus.page, num=locus.num,
                left_index=prev_index, right_index=index,
                left_token_id=tokens[prev_index].token_id, right_token_id=right_id))
        pending = None
        unread = has_unr or "?" in text
        eff = effective_vars(locus.page_vars, tok_tags)
        tokens.append(Token(
            text=text, page=locus.page, num=locus.num,
            locus_type=locus.locus_type, locator=locus.locator,
            category=locus.category, index_in_locus=index,
            span_start=span0, span_end=span1,
            alternatives=tuple(alts), merged_interior=tuple(merged),
            has_alt=bool(alts), has_extended=has_ext, has_ligature=has_lig,
            has_unreadable=unread,
            effective_vars=tuple(sorted(eff.items()))))
        prev_index = index
        reset()

    for e in locus.elements:
        if e.kind in ("white", "comment", "par_start", "par_end"):
            continue
        if e.kind == "text_tag":
            # a mid-locus tag: end the current token first, then apply the tag so
            # only tokens starting at/after this position see the new value
            finish()
            var, val = e.value
            if locus.page_vars.get(var) == "@":
                if val == "@":
                    active_tags.pop(var, None)
                else:
                    active_tags[var] = val
            continue
        if e.kind == "boundary":
            if e.value in split_types:
                finish()
                pending = (e.value, e.start, e.end)
            else:
                merged.append(e.value)
            continue
        piece = _render(e, reading_policy)
        if piece == "" and e.kind == "alt":
            alts.append(e.value)
            continue
        if span0 is None:
            span0 = e.start
            tok_tags = dict(active_tags)     # freeze effective state at token start
        span1 = e.end
        parts.append(piece)
        if e.kind == "alt":
            alts.append(e.value)
        elif e.kind == "highascii":
            has_ext = True
        elif e.kind == "ligature":
            has_lig = True
    finish()

    return LocusTokenization(locus=locus, reading_policy=reading_policy,
                             operation=operation, tokens=tuple(tokens), edges=tuple(edges))


# --------------------------------------------------------------------------
# Davis expansion (named sensitivity view, never canonical)
# --------------------------------------------------------------------------
def davis_pf_form(token: Token) -> Tuple[str, Tuple[str, ...]]:
    """Return the Davis plain p/f expansion of a token surface form + trace.

    Bench/gallows are excluded exactly as in :func:`transforms.expand_plain_pf`.
    This is a *sensitivity* view: never fold it into the canonical stream.
    """
    return expand_plain_pf(token.text)
