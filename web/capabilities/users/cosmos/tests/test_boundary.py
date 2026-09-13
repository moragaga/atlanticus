from __future__ import annotations

import tomllib
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'users' / 'cosmos'


def test_package_depends_only_on_users_core_and_cosmos_connectivity() -> None:
    with (_PACKAGE_ROOT / 'pyproject.toml').open('rb') as source:
        pyproject = tomllib.load(source)

    assert pyproject['project']['dependencies'] == [
        'atlanticus-cosmos==1.0.0',
        'atlanticus-web-users==0.1.0',
    ]


def test_source_does_not_own_provider_configuration_or_provisioning() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in _SOURCE_ROOT.glob('*.py'))

    assert 'atlanticus.connectivity.cosmos' in source
    assert 'atlanticus.web.users' in source
    assert 'azure.' not in source
    assert 'azure_' not in source
    assert 'CosmosSettings' not in source
    assert 'CosmosProvisioner' not in source
    assert 'ensure_containers' not in source
    assert 'ensure_database' not in source
    assert 'upsert_item' not in source
    assert "'users-runtime'" not in source
