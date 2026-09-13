from __future__ import annotations

import tomllib
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'storage' / 'cosmos'


def test_package_depends_only_on_topology_and_cosmos_connectivity() -> None:
    with (_PACKAGE_ROOT / 'pyproject.toml').open('rb') as source:
        pyproject = tomllib.load(source)

    assert pyproject['project']['dependencies'] == [
        'atlanticus-cosmos==1.0.0',
        'atlanticus-web-storage-topology==0.1.0',
    ]


def test_source_uses_connectivity_contract_without_azure_or_users_dependency() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in _SOURCE_ROOT.glob('*.py'))

    assert 'atlanticus.connectivity.cosmos' in source
    assert 'atlanticus.web.storage.topology' in source
    assert 'atlanticus.web.users' not in source
    assert 'azure.' not in source
    assert 'azure_' not in source
    assert 'CosmosClient' not in source
    assert 'CosmosSettings' not in source
