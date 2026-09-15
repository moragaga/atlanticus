import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '__init__.py',
    'ids.py',
    'models.py',
    'module.py',
    'canonical_layout.py',
    'canonical_callbacks.py',
)


def test_canonical_web_commented_mirrors_match_production_behavior() -> None:
    for filename in FILES:
        production = (
            ROOT
            / 'src'
            / 'atlanticus'
            / 'web'
            / 'users'
            / 'configuration'
            / 'web'
            / filename
        )
        commented = (
            ROOT
            / 'commented'
            / 'atlanticus'
            / 'web'
            / 'users'
            / 'configuration'
            / 'web'
            / filename
        )
        production_tree = ast.parse(production.read_text(encoding='utf-8'))
        commented_tree = ast.parse(commented.read_text(encoding='utf-8'))
        assert ast.dump(commented_tree, include_attributes=False) == ast.dump(
            production_tree,
            include_attributes=False,
        )
