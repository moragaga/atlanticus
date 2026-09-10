import ast
from pathlib import Path

FILES = (
    '__init__.py',
    'callbacks.py',
    'ids.py',
    'layout.py',
    'models.py',
    'module.py',
    'presentation.py',
    'query.py',
)


def test_definition_web_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada' / 'web' / 'kpis' / 'definition' / 'web'
    commented = root / 'commented' / 'ada' / 'web' / 'kpis' / 'definition' / 'web'

    for name in FILES:
        productive_tree = ast.parse((productive / name).read_text(encoding='utf-8'))
        commented_tree = ast.parse((commented / name).read_text(encoding='utf-8'))
        assert ast.dump(productive_tree, include_attributes=False) == ast.dump(
            commented_tree,
            include_attributes=False,
        )
