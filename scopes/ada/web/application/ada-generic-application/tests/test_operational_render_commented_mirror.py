from __future__ import annotations

import ast
from pathlib import Path


def test_operational_render_commented_mirror_matches_product_code() -> None:
    package_root = Path(__file__).parents[1]
    product = (
        package_root / 'src' / 'ada' / 'web' / 'application' / 'generic' / 'operational_render.py'
    )
    commented = (
        package_root
        / 'commented'
        / 'ada'
        / 'web'
        / 'application'
        / 'generic'
        / 'operational_render.py'
    )

    product_ast = ast.dump(ast.parse(product.read_text(encoding='utf-8')), include_attributes=False)
    commented_ast = ast.dump(
        ast.parse(commented.read_text(encoding='utf-8')),
        include_attributes=False,
    )

    assert product_ast == commented_ast
