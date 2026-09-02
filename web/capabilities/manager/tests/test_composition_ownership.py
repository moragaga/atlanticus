from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'manager'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'atlanticus' / 'web' / 'manager'


def _imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or '')
    return tuple(modules)


def test_manager_capability_does_not_own_a_web_application_runtime() -> None:
    assert not (_SOURCE_ROOT / 'application.py').exists()
    assert not (_SOURCE_ROOT / 'pages').exists()

    for path in sorted(_SOURCE_ROOT.rglob('*.py')):
        imports = _imported_modules(path)
        assert 'atlanticus.web.application' not in imports
        source = path.read_text(encoding='utf-8')
        assert 'create_web_application' not in source
        assert 'register_page(' not in source


def test_commented_manager_has_no_removed_host_or_pages() -> None:
    assert not (_COMMENTED_ROOT / 'application.py').exists()
    assert not (_COMMENTED_ROOT / 'pages').exists()
