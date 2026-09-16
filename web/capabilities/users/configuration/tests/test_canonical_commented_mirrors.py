import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '__init__.py',
    'canonical.py',
    'errors.py',
    'exchange.py',
    'models.py',
    'schema_v1.py',
    'source_projection.py',
    'source_release.py',
)


def test_canonical_commented_mirrors_match_production_behavior() -> None:
    for filename in FILES:
        production = ROOT / 'src' / 'atlanticus' / 'web' / 'users' / 'configuration' / filename
        commented = ROOT / 'commented' / 'atlanticus' / 'web' / 'users' / 'configuration' / filename
        production_tree = ast.parse(production.read_text(encoding='utf-8'))
        commented_tree = ast.parse(commented.read_text(encoding='utf-8'))
        assert ast.dump(commented_tree, include_attributes=False) == ast.dump(
            production_tree,
            include_attributes=False,
        )
