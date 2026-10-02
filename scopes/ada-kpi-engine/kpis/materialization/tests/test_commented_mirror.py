import ast
from pathlib import Path


def test_commented_mirror_is_semantically_equivalent():
    root = Path(__file__).resolve().parents[1]
    productive = root / 'src/ada/kpis/materialization'
    commented = root / 'commented/ada/kpis/materialization'
    productive_files = {path.relative_to(productive) for path in productive.rglob('*.py')}
    commented_files = {path.relative_to(commented) for path in commented.rglob('*.py')}

    assert productive_files == commented_files
    for relative in productive_files:
        assert ast.dump(
            ast.parse((productive / relative).read_text(encoding='utf-8')),
            include_attributes=False,
        ) == ast.dump(
            ast.parse((commented / relative).read_text(encoding='utf-8')),
            include_attributes=False,
        )
