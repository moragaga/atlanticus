import tomllib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parents[3]


def test_workspace_registers_alarm_runtime_member_and_sources() -> None:
    workspace = tomllib.loads((_BACKEND_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'processes/alarms-runtime' in workspace['tool']['uv']['workspace']['members']
    assert 'ada-command-center-alarms-runtime-process==1.0.0' in workspace['project']['dependencies']
    sources = workspace['tool']['uv']['sources']
    assert sources['ada-command-center-alarms-runtime-process'] == {'workspace': True}
    assert sources['atlanticus-job-runtime']['path'] == '../../../backend/runtime'
    assert sources['atlanticus-operational-data-core']['path'] == '../../operational-data/core'
    assert sources['atlanticus-operational-data-planner']['path'] == '../../operational-data/planner'
