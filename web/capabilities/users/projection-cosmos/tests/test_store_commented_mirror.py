import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / 'src' / 'atlanticus' / 'web' / 'users' / 'projection' / 'cosmos' / 'store.py'
COMMENTED = ROOT / 'commented' / 'atlanticus' / 'web' / 'users' / 'projection' / 'cosmos' / 'store.py'


def test_store_commented_mirror_matches_production_behavior() -> None:
    production_tree = ast.parse(PRODUCTION.read_text(encoding='utf-8'))
    commented_tree = ast.parse(COMMENTED.read_text(encoding='utf-8'))

    assert ast.dump(commented_tree, include_attributes=False) == ast.dump(
        production_tree,
        include_attributes=False,
    )
