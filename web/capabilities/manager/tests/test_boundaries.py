import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src'
COMMENTED_ROOT = PACKAGE_ROOT / 'commented'


def test_commented_mirror_matches_productive_ast() -> None:
    source_files = sorted(path.relative_to(SOURCE_ROOT) for path in SOURCE_ROOT.rglob('*.py'))
    commented_files = sorted(
        path.relative_to(COMMENTED_ROOT) for path in COMMENTED_ROOT.rglob('*.py')
    )

    assert source_files == commented_files
    for relative_path in source_files:
        productive = ast.dump(
            ast.parse((SOURCE_ROOT / relative_path).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        commented = ast.dump(
            ast.parse((COMMENTED_ROOT / relative_path).read_text(encoding='utf-8')),
            include_attributes=False,
        )
        assert commented == productive
