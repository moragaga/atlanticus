import tomllib
from pathlib import Path


def test_core_is_a_workspace_capability_with_neutral_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    scope = root.parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text())
    workspace = tomllib.loads((scope / 'pyproject.toml').read_text())

    assert project['project']['name'] == 'atlanticus-data-producers-core'
    assert project['project']['version'] == '1.0.0'
    assert project['project']['dependencies'] == []
    assert 'producers/core' in workspace['tool']['uv']['workspace']['members']
    assert workspace['tool']['uv']['sources']['atlanticus-data-producers-core'] == {
        'workspace': True
    }
