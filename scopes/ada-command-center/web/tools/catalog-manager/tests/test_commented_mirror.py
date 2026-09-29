import ast
from pathlib import Path


def test_commented_mirror_preserves_productive_behavior() -> None:
    root = Path(__file__).parents[1]
    productive = root / 'src/ada_command_center/web/tools/catalog_manager'
    commented = root / 'commented/ada_command_center/web/tools/catalog_manager'
    for name in ('__init__.py', 'manager.py'):
        assert ast.dump(ast.parse((productive / name).read_text()), include_attributes=False) == (
            ast.dump(ast.parse((commented / name).read_text()), include_attributes=False)
        )
