import ast
from pathlib import Path


def _imported_modules(root: Path) -> tuple[str, ...]:
    modules: list[str] = []
    for source_path in sorted((root / 'src').rglob('*.py')):
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules.append(node.module)
    return tuple(modules)


def test_navigation_configuration_is_independent_from_profiles_users_and_ada() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    modules = _imported_modules(root)

    assert 'atlanticus-web-profiles' not in pyproject
    assert not any(module.startswith('atlanticus.web.profiles') for module in modules)
    assert 'atlanticus-web-users' not in pyproject
    assert not any(module.startswith('atlanticus.web.users') for module in modules)
    assert not any(module == 'ada' or module.startswith('ada.') for module in modules)
