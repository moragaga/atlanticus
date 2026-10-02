from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_persistence_has_no_cloud_client_or_configuration_ownership() -> None:
    text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'src').rglob('*.py'))
    for token in ('CosmosClient', 'DefaultAzureCredential', 'connection_string', '.env'):
        assert token not in text
