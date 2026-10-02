import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
PRODUCTION = ROOT / 'src/ada/kpis/delivery'
COMMENTED = ROOT / 'commented/ada/kpis/delivery'


def test_commented_mirror_is_ast_equivalent() -> None:
    for production in sorted(PRODUCTION.glob('*.py')):
        mirror = COMMENTED / production.name
        assert mirror.is_file(), production.name
        production_ast = ast.dump(
            ast.parse(production.read_text(encoding='utf-8')), include_attributes=False
        )
        mirror_ast = ast.dump(
            ast.parse(mirror.read_text(encoding='utf-8')), include_attributes=False
        )
        assert mirror_ast == production_ast, production.name
