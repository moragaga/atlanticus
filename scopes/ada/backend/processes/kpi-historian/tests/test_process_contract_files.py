from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_process_contract_files_exist() -> None:
    for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
        assert (ROOT / name).is_file()
