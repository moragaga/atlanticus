from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'manager'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'atlanticus' / 'web' / 'manager'


def test_manager_capability_has_no_standalone_application_runtime() -> None:
    assert not (_SOURCE_ROOT / 'application.py').exists()
    assert not (_SOURCE_ROOT / 'pages').exists()


def test_productive_and_commented_python_trees_match() -> None:
    productive_files = sorted(path.relative_to(_SOURCE_ROOT) for path in _SOURCE_ROOT.rglob('*.py'))
    commented_files = sorted(
        path.relative_to(_COMMENTED_ROOT) for path in _COMMENTED_ROOT.rglob('*.py')
    )
    assert productive_files == commented_files

    for relative in productive_files:
        productive = ast.dump(
            ast.parse((_SOURCE_ROOT / relative).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        commented = ast.dump(
            ast.parse((_COMMENTED_ROOT / relative).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        assert productive == commented
