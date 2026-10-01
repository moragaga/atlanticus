import ast
from pathlib import Path

FILES = (
    '__init__.py',
    '__main__.py',
    'application.py',
    'layout.py',
    'navigation.py',
    'runtime.py',
    'surfaces.py',
    'pages/__init__.py',
    'pages/home.py',
)


def test_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada_command_center' / 'web' / 'application' / 'generic'
    commented = root / 'commented' / 'ada_command_center' / 'web' / 'application' / 'generic'

    for name in FILES:
        productive_tree = ast.parse((productive / name).read_text(encoding='utf-8'))
        commented_tree = ast.parse((commented / name).read_text(encoding='utf-8'))
        assert ast.dump(productive_tree, include_attributes=False) == ast.dump(
            commented_tree,
            include_attributes=False,
        )
