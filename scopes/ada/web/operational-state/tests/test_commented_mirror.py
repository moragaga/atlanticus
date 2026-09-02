from __future__ import annotations

import ast
from pathlib import Path


def test_commented_python_mirror_matches_productive_ast() -> None:
    root = Path(__file__).parents[1]
    productive_root = root / 'src' / 'ada' / 'web' / 'operational_state'
    commented_root = root / 'commented' / 'ada' / 'web' / 'operational_state'

    for productive in sorted(productive_root.glob('*.py')):
        commented = commented_root / productive.name
        assert commented.is_file(), f'Missing commented mirror: {productive.name}'
        assert ast.dump(ast.parse(productive.read_text()), include_attributes=False) == ast.dump(
            ast.parse(commented.read_text()),
            include_attributes=False,
        )
