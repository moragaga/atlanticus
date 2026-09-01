import tomllib
from pathlib import Path


def test_process_contract_files_and_container_entrypoint() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ('.env.detail', 'config.detail.json', 'secrets.detail.json', '.python-version'):
        assert (root / name).is_file()

    with (root / 'pyproject.toml').open('rb') as stream:
        document = tomllib.load(stream)

    assert document['project']['name'] == 'ada-kpi-runtime-process'
    assert document['project']['version'] == '1.0.0'
    assert document['project']['scripts'] == {
        'ada-kpi-runtime': 'ada.processes.kpi_runtime.bootstrap:main'
    }
    assert document['tool']['atlanticus']['container'] == {
        'command': 'ada-kpi-runtime',
        'system-profile': 'base',
    }
