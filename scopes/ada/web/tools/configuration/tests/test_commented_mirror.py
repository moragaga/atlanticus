import ast
from pathlib import Path

FILES = (
    '__init__.py',
    'contracts.py',
    'errors.py',
    'lifecycle.py',
    'models.py',
    'operational.py',
    'projection.py',
    'services.py',
    'source.py',
)


def test_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada' / 'web' / 'tools' / 'configuration'
    commented = root / 'commented' / 'ada' / 'web' / 'tools' / 'configuration'

    for name in FILES:
        productive_tree = ast.parse((productive / name).read_text(encoding='utf-8'))
        commented_tree = ast.parse((commented / name).read_text(encoding='utf-8'))
        assert ast.dump(productive_tree, include_attributes=False) == ast.dump(
            commented_tree,
            include_attributes=False,
        )
