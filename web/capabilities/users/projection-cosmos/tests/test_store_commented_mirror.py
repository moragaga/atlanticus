import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('__init__.py', 'materializer.py', 'store.py')


def test_projection_cosmos_commented_mirrors_match_production_behavior() -> None:
    for filename in FILES:
        production = (
            ROOT
            / 'src'
            / 'atlanticus'
            / 'web'
            / 'users'
            / 'projection'
            / 'cosmos'
            / filename
        )
        commented = (
            ROOT
            / 'commented'
            / 'atlanticus'
            / 'web'
            / 'users'
            / 'projection'
            / 'cosmos'
            / filename
        )
        assert ast.dump(
            ast.parse(production.read_text(encoding='utf-8')),
            include_attributes=False,
        ) == ast.dump(
            ast.parse(commented.read_text(encoding='utf-8')),
            include_attributes=False,
        )
