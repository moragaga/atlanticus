import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTIVE = ROOT / 'src'
COMMENTED = ROOT / 'commented'


def _tree(path: Path) -> str:
    return ast.dump(ast.parse(path.read_text(encoding='utf-8')), include_attributes=False)


def test_commented_mirror_matches_productive_python() -> None:
    productive = {path.relative_to(PRODUCTIVE) for path in PRODUCTIVE.rglob('*.py')}
    commented = {path.relative_to(COMMENTED) for path in COMMENTED.rglob('*.py')}

    assert productive == commented
    for relative in productive:
        assert _tree(PRODUCTIVE / relative) == _tree(COMMENTED / relative)
