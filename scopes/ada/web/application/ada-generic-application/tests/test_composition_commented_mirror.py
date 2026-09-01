from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_PRODUCT_ROOT = _PACKAGE_ROOT / 'src' / 'ada' / 'web' / 'application' / 'generic'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'ada' / 'web' / 'application' / 'generic'
_FILES = ('__init__.py', 'application.py', 'composition.py', 'layout.py', 'runtime.py')


def test_composition_productive_and_commented_files_are_ast_equivalent() -> None:
    for filename in _FILES:
        productive = ast.dump(
            ast.parse((_PRODUCT_ROOT / filename).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        commented = ast.dump(
            ast.parse((_COMMENTED_ROOT / filename).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        assert productive == commented, filename
