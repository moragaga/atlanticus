import ast
from pathlib import Path


def test_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src/atlanticus/web/storage/preparation'
    commented = root / 'commented/atlanticus/web/storage/preparation'
    for name in ('__init__.py', 'core.py'):
        assert ast.dump(ast.parse((productive / name).read_text()), include_attributes=False) == (
            ast.dump(ast.parse((commented / name).read_text()), include_attributes=False)
        )
