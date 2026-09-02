import ast
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_SOURCE_ROOT = _ROOT / 'src' / 'ada_command_center' / 'processes' / 'alarms_runtime'

def test_production_source_contains_no_comments() -> None:
    for path in sorted(_SOURCE_ROOT.glob('*.py')):
        source = path.read_text(encoding='utf-8')
        assert '#' not in source


def test_runtime_uses_only_command_center_namespace() -> None:
    for path in sorted(_SOURCE_ROOT.glob('*.py')):
        source = path.read_text(encoding='utf-8')
        assert 'from ada.' not in source
        assert 'import ada.' not in source
        assert 'ada.processes.alarms_runtime' not in source
        assert 'ada.alarms.' not in source


def test_runtime_does_not_import_deferred_physical_dependencies() -> None:
    forbidden = (
        'atlanticus.operational_data.sources',
        'atlanticus.datasets',
        'atlanticus.state',
        'atlanticus.storage',
        'atlanticus.cosmos',
        'azure',
        'pandas',
        'pyarrow',
    )
    for path in sorted(_SOURCE_ROOT.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith(forbidden)
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith(forbidden) for alias in node.names)


def test_session_uses_operational_data_contracts_without_source_io() -> None:
    source = (_SOURCE_ROOT / 'session.py').read_text(encoding='utf-8')
    assert 'atlanticus.operational_data.core' in source
    assert 'atlanticus.operational_data.planner' in source
    assert 'atlanticus.operational_data.sources' not in source


def test_iteration_exposes_port_without_physical_source_types() -> None:
    source = (_SOURCE_ROOT / 'iteration.py').read_text(encoding='utf-8')
    assert 'class AlarmIterationData(Protocol)' in source
    assert 'class AlarmIterationSourceLoader(Protocol)' in source
    assert 'LoadedDataSources' not in source
    assert 'DataSourceLoader' not in source


def test_job_composition_delegates_to_job_runtime_without_internal_loop() -> None:
    path = _SOURCE_ROOT / 'job_composition.py'
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert 'execute_job' in source
    assert 'time.sleep' not in source
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))


def test_deferred_stage_modules_are_not_landed() -> None:
    for name in ('consumer.py', 'revision_file.py', 'revision_resolution.py', 'revision_resolver.py'):
        assert not (_SOURCE_ROOT / name).exists()
