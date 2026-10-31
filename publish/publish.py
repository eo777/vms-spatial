"""Publish the toolkit to its own GitHub repository.

The research workspace stays out of version control. The published repository holds the toolkit's source tree (the
Python package, the shared JS, the viewer, the tests, the docs) AND the data folders (data/, viewer/data/), so a clone
works at once. The data has no history: releases are squashed by default (site.json "history": "squash"), one orphan
commit per release, force-pushed, old objects pruned, like the app repositories; and .gitattributes marks the data
folders binary (-diff) so they never render as diffs. This script:

1. runs the tests (pytest without the slow ones, and the viewer's node tests) unless --skip-tests;
2. collects every file of the toolkit folder that site.json does not exclude, and refuses any text file that contains
   a local path of this machine (the home folder), and any file over 100 MB;
3. writes them into the repository folder (site_dir in site.json, relative to the toolkit folder), removing files an
   earlier run wrote and this one no longer produces, with .gitattributes, VERSION and publish_manifest.json;
4. with --commit, commits: squashed (default) or, with --keep-history, as an ordinary commit with a tag; with --push,
   pushes (force-push for a squashed release).

    python publish/publish.py --dry-run
    python publish/publish.py --commit --push
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import posixpath
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLKIT = HERE.parent
VERSION = 'VERSION'
MANIFEST = 'publish_manifest.json'
ATTRIBUTES = '.gitattributes'
MAX_FILE, WARN_FILE = 100 * 2 ** 20, 50 * 2 ** 20
_HOME = Path.home().parts[-2:]
LOCAL_PATHS = sorted({(_HOME[0] + sep + _HOME[1]).lower().encode() for sep in ('/', '\\', '\\\\', '%5c', '%2f')})


class PublishError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def config():
    return json.loads((HERE / 'site.json').read_text(encoding='utf-8'))


def excluded(rel: str, cfg) -> bool:
    rel = rel.replace('\\', '/')
    for pat in cfg['exclude']:
        if fnmatch.fnmatchcase(rel, pat) or fnmatch.fnmatchcase(rel, pat.replace('**/', '')) or any(fnmatch.fnmatchcase(part, pat.rstrip('/*')) for part in rel.split('/')[:-1]):
            return True
    return False


def optional_data_paths() -> set:
    """The data paths of the manifest's optional entries: referenced, never published, even when fetched locally."""
    m = json.loads((TOOLKIT / 'vmsspatial' / 'resources' / 'data_manifest.json').read_text(encoding='utf-8'))
    return {'data/' + e['key'] for e in m['files'] if e.get('optional')}


def collect(cfg) -> dict:
    """site path -> bytes of every file to publish."""
    files = {}
    optional = optional_data_paths()
    for p in sorted(TOOLKIT.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(TOOLKIT).as_posix()
        if rel.startswith('.git/') or rel in (VERSION, MANIFEST, ATTRIBUTES) or excluded(rel, cfg) or rel in optional:
            continue
        files[rel] = p.read_bytes()
    return files


def gitattributes(cfg) -> bytes:
    lines = ['# data folders: stored as published, never shown as diffs']
    lines += ['%s -diff -text linguist-generated' % pat for pat in cfg.get('no_diff', [])]
    lines += ['*.json.gz binary', '*.gz binary']
    return ('\n'.join(lines) + '\n').encode()


def verify(files: dict, cfg) -> tuple:
    problems, warnings = [], []
    exts = tuple(cfg['text_extensions'])
    for rel, data in files.items():
        if len(data) > MAX_FILE:
            problems.append('%s is %.0f MB; GitHub refuses files over 100 MB' % (rel, len(data) / 2 ** 20))
        elif len(data) > WARN_FILE:
            warnings.append('%s is %.0f MB; GitHub warns above 50 MB' % (rel, len(data) / 2 ** 20))
        if rel.endswith(exts) or '.' not in posixpath.basename(rel):
            low = data.lower()
            for needle in LOCAL_PATHS:
                if needle in low:
                    problems.append('%s contains a local path (%s...)' % (rel, needle.decode()))
                    break
    for must in ('README.md', 'LICENSE', 'NOTICE', 'pyproject.toml', 'vmsspatial/__init__.py', 'viewer/index.html', 'js/sources.js', '.gitignore', 'docs/PITFALLS.md'):
        if must not in files:
            problems.append('%s is missing' % must)
    data_files = [p for p in files if p.startswith('data/')]
    if not data_files:
        warnings.append('no data files in data/ (run vmsspatial fetch-data first if the repository should carry the data)')
    return problems, warnings


def next_version(previous, today):
    base = today.strftime('%Y.%m.%d')
    if not previous or not (previous == base or previous.startswith(base + '.')):
        return base
    n = 1 if previous == base else int(previous[len(base) + 1:])
    return '%s.%d' % (base, n + 1)


def git(site_dir, *args, check=True, capture=True):
    r = subprocess.run(['git', '-C', str(site_dir)] + list(args), capture_output=capture, text=True)
    if check and r.returncode:
        raise PublishError('git %s failed:\n%s' % (' '.join(args), (r.stderr or r.stdout or '').strip() if capture else ''))
    return r


def run_tests():
    r = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '-q', '-m', 'not slow', '-p', 'no:cacheprovider'], cwd=TOOLKIT, capture_output=True, text=True)
    if r.returncode:
        raise PublishError('python tests failed; nothing was published.\n' + (r.stdout + r.stderr)[-3000:])
    print('Python tests: ' + r.stdout.strip().splitlines()[-1])
    tests = [str(p.relative_to(TOOLKIT)) for p in sorted((TOOLKIT / 'viewer' / 'test').glob('*.test.js'))]
    r = subprocess.run(['node', '--test'] + tests, cwd=TOOLKIT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        raise PublishError('viewer tests failed; nothing was published.\n' + (r.stdout + r.stderr)[-3000:])
    print('Viewer tests: pass')


def squash(site_dir, version, build, push):
    """One orphan commit holding the release; no tags; force-pushed; old objects pruned."""
    git(site_dir, 'checkout', '-q', '--orphan', 'release-tmp')
    git(site_dir, 'add', '-A')
    git(site_dir, 'commit', '-q', '-m', 'Release %s' % version, '-m', 'Build %s. History not kept.' % build)
    git(site_dir, 'branch', '-D', 'main', check=False)
    git(site_dir, 'branch', '-M', 'main')
    for tag in git(site_dir, 'tag', '--list').stdout.split():
        git(site_dir, 'tag', '-d', tag)
    print('Committed release %s as the only commit on main (no tags).' % version)
    if push:
        if git(site_dir, 'remote', 'get-url', 'origin', check=False).returncode:
            raise PublishError('no origin remote. Add one first:\n  git -C "%s" remote add origin https://github.com/<you>/vms-spatial.git' % site_dir)
        remote_tags = [l.split('refs/tags/')[1] for l in git(site_dir, 'ls-remote', '--tags', 'origin').stdout.splitlines() if 'refs/tags/' in l and not l.endswith('^{}')]
        if remote_tags:
            git(site_dir, 'push', 'origin', '--delete', *remote_tags, capture=False)
        print('Force-pushing main ...')
        git(site_dir, 'push', '--force', '-u', 'origin', 'main', capture=False)
    git(site_dir, 'reflog', 'expire', '--expire=now', '--all')
    git(site_dir, 'gc', '-q', '--prune=now', '--aggressive')
    print('Local history pruned.')


def commit(site_dir, version, build, push):
    git(site_dir, 'add', '-A')
    tag = 'v' + version
    if git(site_dir, 'status', '--porcelain').stdout.strip():
        git(site_dir, 'commit', '-q', '-m', 'Release %s' % version, '-m', 'Build %s.' % build)
        print('Committed release %s.' % version)
    else:
        print('Nothing to commit.')
    if not git(site_dir, 'tag', '--list', tag).stdout.strip():
        git(site_dir, 'tag', '-a', tag, '-m', 'Release %s' % version)
        print('Tagged %s.' % tag)
    if push:
        if git(site_dir, 'remote', 'get-url', 'origin', check=False).returncode:
            raise PublishError('no origin remote. Add one first:\n  git -C "%s" remote add origin https://github.com/<you>/vms-spatial.git' % site_dir)
        print('Pushing to origin ...')
        git(site_dir, 'push', '-u', 'origin', 'main', '--follow-tags', capture=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Assemble the vms-spatial repository from the toolkit folder.')
    ap.add_argument('--site', help='repository folder (default: site_dir in site.json, relative to the toolkit)')
    ap.add_argument('--skip-tests', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='report what would change; write nothing')
    ap.add_argument('--commit', action='store_true')
    ap.add_argument('--push', action='store_true', help='push (implies --commit; a squashed release is force-pushed)')
    ap.add_argument('--keep-history', action='store_true', help='ordinary commit + tag instead of the squashed release')
    args = ap.parse_args(argv)
    cfg = config()
    site_dir = Path(args.site).resolve() if args.site else (TOOLKIT / cfg['site_dir']).resolve()
    try:
        if site_dir == TOOLKIT or TOOLKIT in site_dir.parents:
            raise PublishError('the repository folder must be outside the toolkit: %s' % site_dir)
        if not args.skip_tests:
            run_tests()
        files = collect(cfg)
        problems, warnings = verify(files, cfg)
        for w in warnings:
            print('warning: ' + w)
        if problems:
            raise PublishError('the assembled repository has problems; nothing was written.\n  ' + '\n  '.join(problems))
        previous = json.loads((site_dir / MANIFEST).read_text(encoding='utf-8')) if (site_dir / MANIFEST).is_file() else {}
        build = sha256(''.join('%s\t%s\n' % (p, sha256(files[p])) for p in sorted(files)).encode())[:12]
        version = previous['version'] if previous.get('build') == build else next_version(previous.get('version'), date.today())
        files[VERSION] = (version + '\n').encode()
        files[ATTRIBUTES] = gitattributes(cfg)
        manifest = dict(version=version, build=build, date=date.today().isoformat(), history=cfg.get('history', 'squash'), files={p: sha256(files[p]) for p in sorted(files)})
        files[MANIFEST] = (json.dumps(manifest, indent=1) + '\n').encode()
        added = [p for p in files if not (site_dir / p).is_file()]
        changed = [p for p in files if (site_dir / p).is_file() and (site_dir / p).read_bytes() != files[p]]
        removed = [p for p in (previous.get('files') or {}) if p not in files and (site_dir / p).is_file()]
        size = sum(len(v) for v in files.values()) / 2 ** 20
        data_size = sum(len(v) for p, v in files.items() if p.startswith(('data/', 'viewer/data/'))) / 2 ** 20
        print('Release %s (build %s): %d files, %.1f MB (data %.1f MB) -> %s' % (version, build, len(files), size, data_size, site_dir))
        for title, items in (('new', added), ('changed', changed), ('removed', removed)):
            if items:
                print('  %s (%d): %s%s' % (title, len(items), ', '.join(items[:12]), ' ...' if len(items) > 12 else ''))
        if not (added or changed or removed):
            print('  No changes.')
        if args.dry_run:
            print('Dry run: nothing written.')
            return 0
        site_dir.mkdir(parents=True, exist_ok=True)
        repo = (site_dir / '.git').is_dir()
        if not repo:
            git(site_dir, 'init', '-q', '-b', 'main')
            print('Initialized a git repository in %s.' % site_dir)
        for p in added + changed:
            (site_dir / p).parent.mkdir(parents=True, exist_ok=True)
            (site_dir / p).write_bytes(files[p])
        for p in removed:
            (site_dir / p).unlink()
        if args.commit or args.push:
            name = git(site_dir, 'config', 'user.name', check=False).stdout.strip()
            if not name:
                raise PublishError('git needs user.name and user.email for commits')
            if args.keep_history or cfg.get('history') == 'keep':
                commit(site_dir, version, build, args.push)
            else:
                squash(site_dir, version, build, args.push)
        else:
            print('Next: review the repository folder, then rerun with --commit (and --push once a remote is set).')
    except PublishError as e:
        sys.stdout.flush()
        print('publish: %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
