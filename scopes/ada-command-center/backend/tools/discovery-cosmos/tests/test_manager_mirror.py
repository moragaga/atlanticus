import ast
from pathlib import Path


def test_manager_commented_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src' / 'ada_command_center' / 'tools' / 'discovery_cosmos'
    commented = root / 'commented' / 'ada_command_center' / 'tools' / 'discovery_cosmos'
    for name in ('manager.py', '__init__.py'):
        assert ast.dump(ast.parse((productive / name).read_text()), include_attributes=False) == (
            ast.dump(ast.parse((commented / name).read_text()), include_attributes=False)
        )
