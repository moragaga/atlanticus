import ast
from pathlib import Path


def test_commented_mirror_is_semantically_equivalent():
    root = Path(__file__).parents[1]
    productive = root / 'src'
    commented = root / 'commented'
    source_files = {path.relative_to(productive) for path in productive.rglob('*.py')}
    mirror_files = {path.relative_to(commented) for path in commented.rglob('*.py')}
    assert source_files == mirror_files
    for relative in source_files:
        source_tree = ast.dump(
            ast.parse((productive / relative).read_text()), include_attributes=False
        )
        mirror_tree = ast.dump(
            ast.parse((commented / relative).read_text()), include_attributes=False
        )
        assert source_tree == mirror_tree
