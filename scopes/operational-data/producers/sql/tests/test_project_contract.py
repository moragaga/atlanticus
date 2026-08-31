import tomllib
from pathlib import Path


def test_sql_is_a_workspace_capability_with_explicit_core_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    scope = root.parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text())
    workspace = tomllib.loads((scope / 'pyproject.toml').read_text())

    assert project['project']['name'] == 'atlanticus-data-producers-sql'
    assert project['project']['version'] == '1.0.0'
    assert 'atlanticus-data-producers-core==1.0.0' in project['project']['dependencies']
    assert workspace['tool']['uv']['sources']['atlanticus-data-producers-core'] == {
        'workspace': True
    }
    assert 'producers/sql' in workspace['tool']['uv']['workspace']['members']
