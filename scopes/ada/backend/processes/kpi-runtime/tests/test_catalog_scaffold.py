from __future__ import annotations

import ast
from pathlib import Path

from ada.processes.kpi_runtime.catalog import build_catalog
from ada.processes.kpi_runtime.catalog.general.over.specs import OVER_SPECS
from ada.processes.kpi_runtime.catalog.general.specs import SPECS

FORBIDDEN_DISCOVERY_IMPORTS = {'importlib', 'pkgutil'}
FORBIDDEN_DISCOVERY_CALLS = {
    '__import__',
    'glob',
    'iterdir',
    'rglob',
    'scandir',
    'walk',
}


def _catalog_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / 'src'
        / 'ada'
        / 'processes'
        / 'kpi_runtime'
        / 'catalog'
    )


def test_default_catalog_is_composed_from_explicit_general_registration() -> None:
    catalog = build_catalog()

    assert catalog.specs == SPECS == ()
    assert catalog.over_specs == OVER_SPECS == ()


def test_catalog_scaffold_contains_only_agreed_top_level_areas() -> None:
    root = _catalog_root()

    for name in ('general', 'mina', 'planta', 'shared'):
        assert (root / name).is_dir()
    assert not (root / 'puerto').exists()


def test_general_scaffold_separates_specs_resolvers_logics_and_over() -> None:
    root = _catalog_root() / 'general'

    required = (
        root / 'specs.py',
        root / 'resolvers.py',
        root / 'logics' / '__init__.py',
        root / 'over' / 'specs.py',
        root / 'over' / 'resolvers.py',
        root / 'over' / 'logics' / '__init__.py',
    )
    assert all(path.is_file() for path in required)


def test_shared_owns_only_transversal_logics_scaffold() -> None:
    root = _catalog_root() / 'shared'

    assert (root / 'logics' / '__init__.py').is_file()
    assert not (root / 'specs.py').exists()
    assert not (root / 'resolvers.py').exists()


def test_registry_does_not_use_filesystem_or_dynamic_import_discovery() -> None:
    path = _catalog_root() / 'registry.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = {alias.name.split('.')[0] for alias in node.names}
            assert imported.isdisjoint(FORBIDDEN_DISCOVERY_IMPORTS)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or '').split('.')[0]
            assert module not in FORBIDDEN_DISCOVERY_IMPORTS
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_DISCOVERY_CALLS
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in FORBIDDEN_DISCOVERY_CALLS
