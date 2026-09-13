from __future__ import annotations

import tomllib
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'storage' / 'topology'


def test_package_has_no_runtime_dependencies() -> None:
    with (_PACKAGE_ROOT / 'pyproject.toml').open('rb') as source:
        pyproject = tomllib.load(source)

    assert pyproject['project']['dependencies'] == []


def test_source_does_not_depend_on_provider_or_azure_modules() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in _SOURCE_ROOT.glob('*.py'))

    assert 'atlanticus.connectivity' not in source
    assert 'azure.' not in source
    assert 'azure_' not in source
