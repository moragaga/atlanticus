from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / 'src' / 'atlanticus' / 'web' / 'projection'
COMMENTED = ROOT / 'commented' / 'atlanticus' / 'web' / 'projection'


def test_commented_python_mirror_matches_production_behavior() -> None:
    production_files = sorted(path.relative_to(PRODUCTION) for path in PRODUCTION.glob('*.py'))
    commented_files = sorted(path.relative_to(COMMENTED) for path in COMMENTED.glob('*.py'))

    assert commented_files == production_files
    for relative in production_files:
        production_tree = ast.parse((PRODUCTION / relative).read_text(encoding='utf-8'))
        commented_tree = ast.parse((COMMENTED / relative).read_text(encoding='utf-8'))
        assert ast.dump(commented_tree, include_attributes=False) == ast.dump(
            production_tree,
            include_attributes=False,
        )
