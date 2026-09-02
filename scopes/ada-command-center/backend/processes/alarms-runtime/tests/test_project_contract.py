import tomllib
from pathlib import Path

_ROOT = Path(__file__).parents[1]


def test_project_contract_pins_only_a3_dependencies() -> None:
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']

    assert project['name'] == 'ada-command-center-alarms-runtime-process'
    assert project['version'] == '1.0.0'
    assert project['requires-python'] == '==3.14.2'
    assert project['dependencies'] == [
        'ada-command-center-alarms-core==1.0.0',
        'ada-command-center-alarms-persistence==1.0.0',
        'atlanticus-job-runtime==1.0.0',
        'atlanticus-operational-data-core==1.0.0',
        'atlanticus-operational-data-planner==1.0.0',
    ]


def test_runtime_remains_library_without_process_launcher() -> None:
    source = tomllib.loads((_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'scripts' not in source['project']
    assert 'atlanticus' not in source.get('tool', {})
