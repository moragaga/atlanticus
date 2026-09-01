from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_evaluation_does_not_own_loading_or_source_clients() -> None:
    text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'src').rglob('*.py'))
    for token in ('CosmosClient', 'DataSourceLoader', 'DataRequirementPlanner', 'ada.data.'):
        assert token not in text
