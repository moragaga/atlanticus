import ast
from pathlib import Path

SRC = Path(__file__).parents[1] / 'src/ada/kpis/delivery'


def test_delivery_domain_has_no_runtime_or_infrastructure_imports() -> None:
    forbidden_roots = {
        'azure',
        'cosmos',
        'flask',
        'dash',
        'atlanticus',
        'os',
        'pathlib',
        'subprocess',
    }
    for path in SRC.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split('.')[0] for alias in node.names}
                assert roots.isdisjoint(forbidden_roots), (path.name, roots)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split('.')[0] not in forbidden_roots, (path.name, node.module)


def test_package_does_not_define_process_entrypoint() -> None:
    pyproject = (Path(__file__).parents[1] / 'pyproject.toml').read_text(encoding='utf-8')
    assert '[project.scripts]' not in pyproject
    assert '[tool.atlanticus.container]' not in pyproject
