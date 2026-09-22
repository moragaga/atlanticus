from pathlib import Path


def test_process_uses_conventional_configuration_root() -> None:
    root = Path(__file__).resolve().parents[1]
    bootstrap = (
        root
        / 'src'
        / 'atlanticus'
        / 'operational_data'
        / 'processes'
        / 'blockgrade'
        / 'bootstrap.py'
    ).read_text(encoding='utf-8')

    assert 'configuration_root=root' in bootstrap
    assert 'dotenv_path=' not in bootstrap
