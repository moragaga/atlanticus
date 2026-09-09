import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
PRODUCTIVE = PACKAGE_ROOT / 'src' / 'ada' / 'configuration' / 'kpi_configuration'
COMMENTED = PACKAGE_ROOT / 'commented' / 'ada' / 'configuration' / 'kpi_configuration'


def _semantic(path: Path) -> str:
    return ast.dump(
        ast.parse(path.read_text(encoding='utf-8')),
        include_attributes=False,
    )


def test_commented_python_mirror_matches_productive_package() -> None:
    productive = {path.relative_to(PRODUCTIVE) for path in PRODUCTIVE.rglob('*.py')}
    commented = {path.relative_to(COMMENTED) for path in COMMENTED.rglob('*.py')}
    assert productive == commented
    for relative in productive:
        assert _semantic(PRODUCTIVE / relative) == _semantic(COMMENTED / relative)
