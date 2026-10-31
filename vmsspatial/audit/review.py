"""Reading the alignment review (data/manuscript/spatial_review.json.gz).

The review covers all 39,026 canonical ZL tokens: for each its id (page.locus@span), text, the typed boundary after it,
its assignment group, flags, and the strict / sensitivity eligibility. A group holds the original rectangles (`parts`,
XML pixel frame), their union (`box`), the coordinate spellings and XML indices, the native display rectangles for the
externally hosted page image (`display_parts`), the alignment status, and `resolved` word geometry for compounds and
image-reviewed cuts. Corrections made during the review are already applied; the file carries no log of them.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from .. import paths
from ..bundle import read_json
from .flags import FLAGS, POLICIES


def load_review(path=None) -> dict:
    return read_json(path or paths.resolve('manuscript/spatial_review.json.gz'))


def geometry(review: dict, policy: str = 'strict') -> Dict[str, Optional[list]]:
    """token id -> box (XML pixel frame) or None under a policy ('strict' = word-level only; 'sensitivity' also admits
    shared and spelling-disputed locations as approximations)."""
    if policy not in POLICIES:
        raise ValueError('policy must be strict or sensitivity')
    return {t['id']: t.get('resolved_box', review['groups'][t['group']]['box']) if t[policy] else None for t in review['tokens']}


def package(review: dict, words: List[str], lines: List[dict]) -> dict:
    """The `spatialReview` block of a word bundle: the review's records for the bundle's tokens, joined by whole ZL
    locus (never by spelling alone), with one independently selectable group per resolved word."""
    by_line = defaultdict(list)
    for token in review['tokens']:
        by_line[(token['page'], token['locus'])].append(token)
    ordered = []
    for line in lines:
        tokens = [t for t in by_line[(line['page'], line['locus'])] if '?' not in t['text']]
        assert [t['text'] for t in tokens] == words[line['start']:line['end']], line
        ordered.extend(dict(t) for t in tokens)
    assert len(ordered) == len(words)
    positions = {t['id']: i for i, t in enumerate(ordered)}
    token_by_id = {t['id']: t for t in review['tokens']}
    hard = set(review['policies']['sensitivity_exclusions'])
    groups = {}
    for t in ordered:
        if not t['group'] or t['group'] in groups:
            continue
        g = review['groups'][t['group']]
        members = [token_by_id[i] for i in g['tokens']]
        label = ''.join(m['text'] + (m['after'] if j < len(members) - 1 else '') for j, m in enumerate(members))
        groups[t['group']] = dict(g, positions=[positions[i] for i in g['tokens'] if i in positions], label=label,
                                  safe=bool(g['box'] and not hard.intersection(g['flags'])))
    clean = geometry(review)
    sensitivity = geometry(review, 'sensitivity')
    for key, g in list(groups.items()):
        if not g.get('resolved'):
            continue
        del groups[key]
        for r in g['resolved']:
            if r['token'] not in positions:
                continue
            pos = positions[r['token']]
            child = key + ':' + r['token']
            ordered[pos]['group'] = child
            token = ordered[pos]
            groups[child] = dict(g, id=child, source_group=key, tokens=[r['token']], positions=[pos], box=r['box'], parts=[r['box']],
                                 display_parts=[r['display_box']], xml_indices=r['xml_indices'], source_parts=g['parts'],
                                 source_display_parts=g.get('display_parts'), label=token['text'] + (',' if token['after'] == ',' else ''),
                                 resolution=r, safe=True)
    return dict(version=review['version'], tokens=ordered, groups=groups,
                geometry=[clean[t['id']] for t in ordered], sensitivityGeometry=[sensitivity[t['id']] for t in ordered])


def token_table(review: dict, pages=None) -> List[dict]:
    """One row per token: id, page, locus, locus_type, text, after, boundary, group, status, xml_words, xml_indices,
    flags, strict, sensitivity, box."""
    out = []
    for t in review['tokens']:
        if pages and t['page'] not in pages:
            continue
        g = review['groups'].get(t['group'], {}) if t['group'] else {}
        out.append(dict(id=t['id'], page=t['page'], locus=t['locus'], locus_type=t['locus_type'], text=t['text'], after=t['after'],
                        boundary=t['boundary'], group=t['group'], status=g.get('status'),
                        xml_words=' '.join(g.get('xml_words', [])), xml_indices=','.join(map(str, g.get('xml_indices', []))),
                        flags='|'.join(t['flags']), strict=t['strict'], sensitivity=t['sensitivity'],
                        box=t.get('resolved_box', g.get('box'))))
    return out


def flagged_tokens(review: dict, flags=None, pages=None) -> List[dict]:
    rows = token_table(review, pages)
    want = set(flags) if flags else None
    return [r for r in rows if r['flags'] and (want is None or want & set(r['flags'].split('|')))]


def write_csv(rows: List[dict], path, fields=None):
    fields = fields or [k for k in rows[0].keys() if k != 'box'] if rows else []
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def page_summary(review: dict) -> Dict[str, dict]:
    out = {}
    for t in review['tokens']:
        s = out.setdefault(t['page'], dict(tokens=0, strict=0, sensitivity=0, flags=Counter()))
        s['tokens'] += 1
        s['strict'] += int(t['strict'])
        s['sensitivity'] += int(t['sensitivity'])
        s['flags'].update(t['flags'])
    return {p: dict(s, flags=dict(s['flags'])) for p, s in out.items()}


def describe_token(review: dict, token_id: str) -> dict:
    by_id = {t['id']: t for t in review['tokens']}
    t = by_id[token_id]
    g = review['groups'].get(t['group']) if t['group'] else None
    out = dict(token=t, flags={f: FLAGS.get(f, ('?', f))[1] for f in t['flags']}, group=None)
    if g:
        members = [by_id[i] for i in g['tokens']]
        out['group'] = dict(id=g['id'], label=''.join(m['text'] + (m['after'] if j < len(members) - 1 else '') for j, m in enumerate(members)),
                            tokens=g['tokens'], xml_words=g['xml_words'], xml_indices=g['xml_indices'], parts=g['parts'], box=g['box'],
                            display_parts=g.get('display_parts'), status=g['status'], resolved=g.get('resolved'))
        page = review['pages'].get(g['page'], {})
        out['image'] = page.get('display_image')
    return out


def metrics(review: dict) -> dict:
    return {k: v for k, v in review['metrics'].items() if k != 'per_page'}
