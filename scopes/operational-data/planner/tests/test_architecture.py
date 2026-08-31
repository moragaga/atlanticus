from pathlib import Path


def test_planner_only_depends_on_operational_data_core() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'dependencies = ["atlanticus-operational-data-core==1.0.0"]' in pyproject

    source = '\n'.join(path.read_text() for path in (root / 'src').rglob('*.py'))
    forbidden = (
        'ada.',
        'atlanticus.connectivity',
        'atlanticus.datasets',
        'atlanticus.integrations',
        'atlanticus.runtime',
        'pandas',
        'pyarrow',
    )
    for token in forbidden:
        assert token not in source
