import ast
from pathlib import Path

FILES = (
    '__init__.py',
    '__main__.py',
    'access.py',
    'application.py',
    'composition.py',
    'dependencies.py',
    'kpi_definitions.py',
    'kpis.py',
    'local_runtime.py',
    'tool_kpi_registry_destinations.py',
    'tools.py',
    'workflows.py',
    'workspace.py',
)


def test_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    commented = root / 'commented' / 'ada' / 'web' / 'application' / 'configuration_manager'

    for name in FILES:
        productive_tree = ast.parse((productive / name).read_text(encoding='utf-8'))
        commented_tree = ast.parse((commented / name).read_text(encoding='utf-8'))
        assert ast.dump(productive_tree, include_attributes=False) == ast.dump(
            commented_tree,
            include_attributes=False,
        )
