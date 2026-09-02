import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_ROOT = _PACKAGE_ROOT / 'src/ada_command_center/alarms/persistence'
_EXPECTED_PRODUCTION_FILES = {
    '__init__.py',
    'errors.py',
    'journal.py',
    'models.py',
    'paths.py',
    'serialization.py',
    'store.py',
}


def _import_names(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    return tuple(names)


def test_persistence_has_expected_production_files() -> None:
    actual = {path.name for path in _ROOT.glob('*.py')}
    assert actual == _EXPECTED_PRODUCTION_FILES


def test_persistence_keeps_runtime_and_external_infrastructure_out_of_domain_storage() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in _ROOT.glob('*.py'))

    assert 'ada_command_center.processes' not in source
    assert 'atlanticus.runtime' not in source
    assert 'atlanticus.configuration' not in source
    assert 'os.environ' not in source
    assert 'cosmos' not in source.lower()
    assert 'redis' not in source.lower()
    assert 'azure' not in source.lower()


def test_persistence_only_uses_json_and_state_from_atlanticus() -> None:
    for path in sorted(_ROOT.glob('*.py')):
        for name in _import_names(path):
            if name == 'ada' or name.startswith('ada.'):
                raise AssertionError(f'legacy ADA import is not allowed: {name}')
            if name.startswith('atlanticus.'):
                assert name.startswith(('atlanticus.json', 'atlanticus.state'))


def test_persistence_reuses_atlanticus_json_and_state_primitives() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in _ROOT.glob('*.py'))

    assert 'atlanticus.json' in source
    assert 'atlanticus.state' in source
    assert 'AtomicJsonStore' in source
