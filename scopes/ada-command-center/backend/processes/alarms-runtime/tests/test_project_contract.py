import tomllib
from pathlib import Path

_ROOT = Path(__file__).parents[1]


def test_project_contract_pins_required_dependencies() -> None:
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['name'] == 'ada-command-center-alarms-runtime-process'
    assert project['version'] == '1.0.0'
    assert project['requires-python'] == '==3.14.2'
    assert project['dependencies'] == [
        'ada-command-center-alarms-domain==1.0.0',
        'ada-command-center-alarms-core==1.0.0',
        'ada-command-center-alarms-materialization==1.0.0',
        'ada-command-center-alarms-persistence==1.0.0',
        'atlanticus-configuration==1.0.0',
        'atlanticus-datasets-parquet==1.0.0',
        'atlanticus-datasets-runtime==1.0.0',
        'atlanticus-job-runtime==1.0.0',
        'atlanticus-key-vault==1.0.0',
        'atlanticus-observability-azure==1.0.0',
        'atlanticus-operational-data-core==1.0.0',
        'atlanticus-operational-data-planner==1.0.0',
        'atlanticus-operational-data-sources==1.0.0',
        'atlanticus-state==1.0.0',
    ]


def test_runtime_process_exposes_executable_command() -> None:
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['scripts'] == {
        'ada-command-center-alarms-runtime': (
            'ada_command_center.processes.alarms_runtime.bootstrap:main'
        ),
    }
