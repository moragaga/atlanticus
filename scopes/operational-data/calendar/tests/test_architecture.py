from __future__ import annotations

import ast
from pathlib import Path


def test_calendar_is_scope_owned_and_infrastructure_free() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'dependencies = []' in pyproject

    for path in (root / 'src').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert 'ada.' not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module,)
            else:
                continue
            assert not any(
                name.startswith(('atlanticus.connectivity', 'atlanticus.integrations'))
                for name in names
            )
