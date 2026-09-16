from __future__ import annotations

import tomllib
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_package_depends_only_on_users_core_and_cosmos_connectivity() -> None:
    with (_PACKAGE_ROOT / 'pyproject.toml').open('rb') as source:
        pyproject = tomllib.load(source)

    assert pyproject['project']['dependencies'] == [
        'atlanticus-cosmos==1.0.0',
        'atlanticus-web-users==0.1.0',
    ]


