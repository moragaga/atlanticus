import ast
from pathlib import Path

FILES = (
    '__init__.py',
    'configuration.py',
    'definition.py',
    'errors.py',
    'models.py',
)


def test_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada_command_center' / 'domain' / 'alarms'
    commented = root / 'commented' / 'ada_command_center' / 'domain' / 'alarms'

    for name in FILES:
        productive_tree = ast.parse((productive / name).read_text(encoding='utf-8'))
        commented_tree = ast.parse((commented / name).read_text(encoding='utf-8'))
        assert ast.dump(productive_tree, include_attributes=False) == ast.dump(
            commented_tree,
            include_attributes=False,
        )
