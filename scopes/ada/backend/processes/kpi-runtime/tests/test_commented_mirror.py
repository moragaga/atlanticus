from __future__ import annotations

import ast
from pathlib import Path


def _semantic(path: Path) -> str:
    return ast.dump(ast.parse(path.read_text(encoding='utf-8')), include_attributes=False)


def test_commented_mirror_is_semantically_equivalent() -> None:
    root = Path(__file__).resolve().parents[1]
    productive = root / 'src'
    commented = root / 'commented'
    productive_files = {path.relative_to(productive) for path in productive.rglob('*.py')}
    commented_files = {path.relative_to(commented) for path in commented.rglob('*.py')}

    assert productive_files == commented_files
    for relative in productive_files:
        assert _semantic(productive / relative) == _semantic(commented / relative)
