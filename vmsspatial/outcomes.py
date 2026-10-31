"""Per-token repetition outcomes: what a spatial measure is tested against.

    app_impact   share of the complete `w`-token windows containing N in which another copy of N's spelling occurs
                 (the heatmap's "word repetition impact"; the exact gain of replacing this one occurrence by a fresh spelling)
    arrival      1 - 1 / copies of N's spelling among N and the w-1 tokens before it (arrival burden)
    repeat       N's spelling occurs among the w-1 tokens before it
    departure    the mirror of arrival: N and the w-1 tokens after it
    full         both ends of N's windows lie inside the stretch of N's bifolium that holds N (the cohort of the
                 within-bifolium contrasts; in a sheet order that stretch is the whole sheet)
``word_impact`` is the complete port of ``js/heatmap_math.js`` ``wordImpact`` (windows, affected, gain, step change).
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

import numpy as np


def occurrence_arrays(words):
    n = len(words)
    prev = np.full(n, -1)
    nxt = np.full(n, n)
    last = {}
    for i, w in enumerate(words):
        j = last.get(w)
        if j is not None:
            prev[i] = j
            nxt[j] = i
        last[w] = i
    return prev, nxt


def outcomes(words, bstart=None, bend=None, w=100) -> Dict[str, np.ndarray]:
    n = len(words)
    prev, nxt = occurrence_arrays(words)
    idx = np.arange(n)
    repeat = ((idx - prev <= w - 1) & (prev >= 0)).astype(float)
    arrival = np.zeros(n)
    counts = Counter()
    for i in range(n):
        counts[words[i]] += 1
        if i >= w:
            counts[words[i - w]] -= 1
        arrival[i] = 1 - 1 / counts[words[i]]
    departure = np.zeros(n)
    counts = Counter()
    for i in range(n - 1, -1, -1):
        counts[words[i]] += 1
        if i + w < n:
            counts[words[i + w]] -= 1
        departure[i] = 1 - 1 / counts[words[i]]
    lo = np.maximum(0, idx - (w - 1))
    hi = np.minimum(idx, n - w)
    count = np.maximum(0, hi - lo + 1)
    unique = np.maximum(0, np.minimum(hi, nxt - w) - np.maximum(lo, prev + 1) + 1)
    app = np.where(count > 0, (count - unique) / np.maximum(count, 1), np.nan)
    out = dict(app_impact=app, arrival=arrival, repeat=repeat, repeat100=repeat, departure=departure)
    if bstart is not None:
        out['full'] = (idx - bstart >= w - 1) & (bend - idx >= w)
    return out


def word_impact(words, width=100) -> Dict[str, np.ndarray]:
    """For every token: windows (complete windows containing it), affected (those with another copy of its spelling),
    gain (affected / (windows * width)), and the step change of the backward window when the token arrives: enter (a new
    type arrives), leave (the last copy of the outgoing token leaves), change = (enter - leave) / width."""
    n = len(words)
    prev, nxt = occurrence_arrays(words)
    windows = np.zeros(n, dtype=np.int64)
    affected = np.zeros(n, dtype=np.int64)
    gain = np.full(n, np.nan)
    change = np.full(n, np.nan)
    enter = np.zeros(n, dtype=np.int8)
    leave = np.zeros(n, dtype=np.int8)
    for i in range(n):
        lo, hi = max(0, i - width + 1), min(i, n - width)
        count = max(0, hi - lo + 1)
        unique = max(0, min(hi, nxt[i] - width) - max(lo, prev[i] + 1) + 1)
        windows[i] = count
        affected[i] = count - unique
        if count:
            gain[i] = affected[i] / (count * width)
        if i >= width:
            enter[i] = 1 if prev[i] < i - width + 1 else 0
            leave[i] = 1 if nxt[i - width] >= i else 0
            change[i] = (enter[i] - leave[i]) / width
    return dict(previous=prev, next=nxt, windows=windows, affected=affected, gain=gain, change=change, enter=enter, leave=leave)


def token_meta(ms, line_words):
    """node, group per token and the token range (bstart, bend) of the contiguous stretch of its bifolium in the
    stream: the whole sheet in a sheet order, one of its stretches in page order, where its pages lie apart. Statistics
    by sheet use the `node` labels, which hold in any order."""
    node, group = [], []
    for L, ws in zip(ms.lines, line_words):
        node += [L['node']] * len(ws)
        group += [L['group']] * len(ws)
    node = np.array(node, dtype=object)
    group = np.array(group, dtype=object)
    n = len(node)
    bstart = np.zeros(n, dtype=int)
    bend = np.zeros(n, dtype=int)
    i = 0
    while i < n:
        j = i
        while j < n and node[j] == node[i]:
            j += 1
        bstart[i:j] = i
        bend[i:j] = j
        i = j
    return node, group, bstart, bend


def token_lengths(words) -> np.ndarray:
    return np.array([len(w) for w in words])


def line_positions(line_words) -> dict:
    """Per token: position in its line, line length, and the line's index within its page (needs a Manuscript for the
    latter; see interior cohorts in stats.py)."""
    pos = np.concatenate([np.arange(len(ws)) for ws in line_words]) if line_words else np.zeros(0, int)
    ln = np.concatenate([np.full(len(ws), len(ws)) for ws in line_words]) if line_words else np.zeros(0, int)
    return dict(pos=pos, linelen=ln)


def repeat_outside_pool(words, pools, w=99, same_line_excluded=None) -> np.ndarray:
    """1 when another token of N's spelling lies within `w` tokens before or after N and OUTSIDE N's pool (the overlap
    test of 28 October 2026: when the predictor pools the words beside N and the outcome counts a twin anywhere, both can
    read the same few words). `pools`: a function i -> Pool, or a sequence of index arrays. `same_line_excluded`: an
    optional per-token line index; twins on N's own line are then ignored as well (the stricter column)."""
    n = len(words)
    positions = {}
    for i, x in enumerate(words):
        positions.setdefault(x, []).append(i)
    out = np.zeros(n, dtype=np.int8)
    for i in range(n):
        P = positions[words[i]]
        if len(P) == 1:
            continue
        p = pools(i) if callable(pools) else pools[i]
        inside = set(np.asarray(getattr(p, 'indices', p)).tolist())
        for j in P:
            if j < i - w:
                continue
            if j > i + w:
                break
            if j != i and j not in inside and (same_line_excluded is None or same_line_excluded[j] != same_line_excluded[i]):
                out[i] = 1
                break
    return out
