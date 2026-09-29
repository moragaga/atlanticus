from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename', ['__init__.py', 'connections.py', 'discovery.py'])
def test_comment_mirrors_are_equivalent(filename: str) -> None:
    source = _ROOT / 'src/ada_command_center/tools/discovery_cosmos' / filename
    commented = _ROOT / 'commented/ada_command_center/tools/discovery_cosmos' / filename
    assert ast.dump(ast.parse(source.read_text(encoding='utf-8'))) == ast.dump(
        ast.parse(commented.read_text(encoding='utf-8'))
    )
