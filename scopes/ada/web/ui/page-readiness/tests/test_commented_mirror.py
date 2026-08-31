from __future__ import annotations

import ast
from pathlib import Path


def test_python_commented_tree_is_behaviorally_equivalent() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / 'src' / 'ada' / 'web' / 'ui' / 'page_readiness'
    commented_root = project_root / 'commented' / 'ada' / 'web' / 'ui' / 'page_readiness'
    source_files = sorted(path.relative_to(source_root) for path in source_root.rglob('*.py'))
    commented_files = sorted(
        path.relative_to(commented_root) for path in commented_root.rglob('*.py')
    )

    assert commented_files == source_files
    for relative in source_files:
        source_ast = ast.dump(
            ast.parse((source_root / relative).read_text()), include_attributes=False
        )
        commented_ast = ast.dump(
            ast.parse((commented_root / relative).read_text()), include_attributes=False
        )
        assert commented_ast == source_ast, relative


def test_non_python_asset_lists_are_equivalent() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for relative in ('resources/css/css.list', 'resources/js/js.list'):
        source = project_root / 'src/ada/web/ui/page_readiness' / relative
        commented = project_root / 'commented/ada/web/ui/page_readiness' / relative
        assert source.read_bytes() == commented.read_bytes()


def _without_comment_only_lines(text: str, prefix: str) -> str:
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith(prefix))


def _without_css_comment_blocks(text: str) -> str:
    import re

    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def _normalized_asset(text: str) -> str:
    return ' '.join(text.split())


def test_javascript_commented_mirror_preserves_runtime_code() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = project_root / 'src/ada/web/ui/page_readiness/resources/js/10-page-readiness.js'
    commented = (
        project_root / 'commented/ada/web/ui/page_readiness/resources/js/10-page-readiness.js'
    )

    assert _normalized_asset(source.read_text()) == _normalized_asset(
        _without_comment_only_lines(commented.read_text(), '//')
    )


def test_css_commented_mirror_preserves_runtime_rules() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = project_root / 'src/ada/web/ui/page_readiness/resources/css/10-page-readiness.css'
    commented = (
        project_root / 'commented/ada/web/ui/page_readiness/resources/css/10-page-readiness.css'
    )

    assert _normalized_asset(source.read_text()) == _normalized_asset(
        _without_css_comment_blocks(commented.read_text())
    )
