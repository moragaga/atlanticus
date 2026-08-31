from pathlib import Path


def test_sources_depend_on_operational_data_layers_not_consumer_domains() -> None:
    root = Path(__file__).resolve().parents[1]
    source = '\n'.join(path.read_text() for path in (root / 'src').rglob('*.py'))
    forbidden = (
        'ada.',
        'atlanticus.operational_data.processes',
        'atlanticus.datasets.runtime',
    )
    for token in forbidden:
        assert token not in source
