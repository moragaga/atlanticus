import tomllib
from pathlib import Path


def test_process_is_owned_by_operational_data_workspace() -> None:
    root = Path(__file__).resolve().parents[1]
    scope = root.parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    workspace = tomllib.loads((scope / 'pyproject.toml').read_text(encoding='utf-8'))

    assert project['project']['name'] == 'atlanticus-operational-data-pi-process'
    assert project['project']['version'] == '1.0.0'
    assert project['project']['dependencies'] == [
        'atlanticus-configuration==1.0.0',
        'atlanticus-data-producers-pi==1.0.0',
        'atlanticus-http==1.0.0',
        'atlanticus-job-runtime==1.0.0',
        'atlanticus-kernel==1.0.0',
        'atlanticus-key-vault==1.0.0',
        'atlanticus-observability-azure==1.0.0',
        'atlanticus-pi-contracts==1.0.0',
        'atlanticus-pi-web-api==1.0.0',
    ]
    assert project['project']['scripts'] == {
        'operational-data-pi': 'atlanticus.operational_data.processes.pi.bootstrap:main'
    }
    assert project['tool']['atlanticus']['container']['command'] == 'operational-data-pi'
    assert 'tool' in workspace
    assert 'processes/pi' in workspace['tool']['uv']['workspace']['members']
    assert workspace['tool']['uv']['sources']['atlanticus-operational-data-pi-process'] == {
        'workspace': True
    }
    assert 'sources' not in project.get('tool', {}).get('uv', {})


def test_process_uses_conventional_configuration_root() -> None:
    root = Path(__file__).resolve().parents[1]
    bootstrap = (
        root / 'src' / 'atlanticus' / 'operational_data' / 'processes' / 'pi' / 'bootstrap.py'
    ).read_text(encoding='utf-8')

    assert 'configuration_root=root' in bootstrap
    assert 'dotenv_path=' not in bootstrap


def test_process_keeps_reference_templates_without_real_local_env() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / '.python-version').read_text(encoding='utf-8').strip() == '3.14.2'
    assert (root / '.env.detail').is_file()
    assert (root / 'config.detail.json').is_file()
    assert (root / 'secrets.detail.json').is_file()
    assert not (root / '.env').exists()
    assert not (root / 'uv.lock').exists()
    assert not (root / 'scripts').exists()
    assert not (root / 'FIRST_STEP.txt').exists()
