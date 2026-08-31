from __future__ import annotations

import ast
from pathlib import Path


def test_data_core_has_no_runtime_or_infrastructure_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'dependencies = []' in pyproject

    forbidden_prefixes = (
        'ada.',
        'atlanticus.connectivity',
        'atlanticus.datasets',
        'atlanticus.integrations',
        'atlanticus.runtime',
        'azure',
        'flask',
        'httpx',
        'pandas',
        'pyarrow',
        'requests',
    )
    for path in (root / 'src').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module,)
            else:
                continue
            assert not any(
                name == prefix or name.startswith(prefix)
                for name in names
                for prefix in forbidden_prefixes
            ), f'{path}: forbidden infrastructure import {names}'
