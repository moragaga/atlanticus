from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'ada' / 'web' / 'kpis' / 'collector'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'ada' / 'web' / 'kpis' / 'collector'


@pytest.mark.parametrize(
    'filename',
    (
        '__init__.py',
        'collector.py',
        'contracts.py',
        'cosmos.py',
        'integration.py',
        'models.py',
        'presentation.py',
        'runtime.py',
    ),
)
def test_commented_mirror_has_equivalent_python_ast(filename: str) -> None:
    source = ast.dump(ast.parse((_SOURCE_ROOT / filename).read_text()), include_attributes=False)
    commented = ast.dump(
        ast.parse((_COMMENTED_ROOT / filename).read_text()),
        include_attributes=False,
    )

    assert commented == source
