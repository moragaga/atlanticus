from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'manager'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'atlanticus' / 'web' / 'manager'
_CSS_PATH = _SOURCE_ROOT / 'resources' / 'css' / '10_manager.css'

_REMOVED_NAMES = {
    'ManagerApplicationDefinition',
    'ManagerBrand',
    'ManagerBrandMark',
    'build_manager_header',
    'REFRESH_BUTTON_ID',
}

_DEAD_CSS_SELECTORS = (
    '.atlanticus-manager--standalone',
    '.atlanticus-manager__header',
    '.atlanticus-manager__header-identity',
    '.atlanticus-manager__header-actions',
    '.atlanticus-manager__brand-supporting',
    '.atlanticus-manager__brand-mark',
    '.atlanticus-manager__title',
    '.atlanticus-manager__button--header',
)


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_standalone_application_contract_is_absent() -> None:
    models = _defined_names(_SOURCE_ROOT / 'models.py')
    layout = _defined_names(_SOURCE_ROOT / 'web' / 'layout.py')
    ids = _defined_names(_SOURCE_ROOT / 'web' / 'ids.py')

    assert _REMOVED_NAMES.isdisjoint(models | layout | ids)


def test_manager_public_api_does_not_export_removed_host_contract() -> None:
    source = (_SOURCE_ROOT / '__init__.py').read_text(encoding='utf-8')
    web_source = (_SOURCE_ROOT / 'web' / '__init__.py').read_text(encoding='utf-8')

    for name in _REMOVED_NAMES:
        assert name not in source
        assert name not in web_source


def test_standalone_header_css_is_absent() -> None:
    css = _CSS_PATH.read_text(encoding='utf-8')
    for selector in _DEAD_CSS_SELECTORS:
        assert selector not in css


def test_surface_contract_remains_available() -> None:
    models = _defined_names(_SOURCE_ROOT / 'models.py')
    surface = _defined_names(_SOURCE_ROOT / 'surface.py')

    assert 'ManagerSurfaceDefinition' in models
    assert 'ManagerSurface' in surface


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
