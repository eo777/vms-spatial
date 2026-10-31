"""The data manifest: shipped files travel with the repository, optional files are only referenced."""
from conftest import needs_data

from vmsspatial import paths
from vmsspatial.datafiles import verify, selected, is_optional


def test_manifest_entries_are_complete_and_sourced():
    m = paths.manifest()
    keys = [e['key'] for e in m['files']]
    assert len(keys) == len(set(keys))
    for e in m['files']:
        assert e['sha256'] and e['bytes'] > 0 and e['group'], e['key']
        assert e.get('url') or e.get('workspace'), e['key']            # every file has a place to come from
    shipped = [e for e in m['files'] if not is_optional(e)]
    optional = [e for e in m['files'] if is_optional(e)]
    assert sum(e['bytes'] for e in shipped) < 24 * 1024 * 1024         # the repository stays small (the coordinate products added about 2.5 MB in 2026-10)
    assert len(optional) >= 229 and all(e['group'] in ('raw', 'model', 'reference', 'images') for e in optional)
    assert all(e['key'].startswith('raw/positional-data/') for e in optional if e['group'] == 'raw' and e['key'].endswith('.xml'))
    assert not any(is_optional(e) for e in selected())                   # a plain fetch never pulls an optional file
    assert any(is_optional(e) for e in selected(['images']))             # a named group includes its optional files
    assert all(is_optional(e) or e in list(selected()) for e in selected(optional=True))


@needs_data
def test_shipped_files_are_present_and_verified():
    v = verify()
    assert not v['missing'] and not v['bad'], (v['missing'], v['bad'])
