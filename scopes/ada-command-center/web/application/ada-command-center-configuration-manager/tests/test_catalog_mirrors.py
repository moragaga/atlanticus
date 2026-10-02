import ast
from pathlib import Path


def test_new_commented_mirrors_match_productive_ast() -> None:
    root = Path(__file__).parents[1]
    src = root / 'src/ada_command_center/web/application/configuration_manager'
    commented = root / 'commented/ada_command_center/web/application/configuration_manager'
    for name in (
        'catalog_configuration.py',
        'durable_runtime.py',
        'deployment.py',
        'composition.py',
        'dependencies.py',
        '__main__.py',
    ):
        assert ast.dump(ast.parse((src / name).read_text()), include_attributes=False) == (
            ast.dump(ast.parse((commented / name).read_text()), include_attributes=False)
        )
