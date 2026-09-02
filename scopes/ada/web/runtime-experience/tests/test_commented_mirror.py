from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).parents[1]
_PRODUCTIVE_ROOT = _PACKAGE_ROOT / 'src' / 'ada' / 'web' / 'runtime_experience'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'ada' / 'web' / 'runtime_experience'


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding='utf-8'))


def test_commented_mirror_matches_productive_python_ast() -> None:
    productive_files = tuple(
        sorted(path.relative_to(_PRODUCTIVE_ROOT) for path in _PRODUCTIVE_ROOT.rglob('*.py'))
    )
    commented_files = tuple(
        sorted(path.relative_to(_COMMENTED_ROOT) for path in _COMMENTED_ROOT.rglob('*.py'))
    )

    assert commented_files == productive_files
    for relative_path in productive_files:
        assert ast.dump(_tree(_COMMENTED_ROOT / relative_path)) == ast.dump(
            _tree(_PRODUCTIVE_ROOT / relative_path)
        )
