import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION_ROOT = _PACKAGE_ROOT / 'src/ada_command_center/alarms/core'
_EXPECTED_PRODUCTION_FILES = {
    '__init__.py',
    'commit.py',
    'deactivation.py',
    'errors.py',
    'evaluation.py',
    'evidence.py',
    'journey.py',
    'lifecycle.py',
    'management.py',
    'models.py',
    'priority.py',
    'routing.py',
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


def test_core_has_expected_production_files() -> None:
    actual = {path.name for path in _PRODUCTION_ROOT.glob('*.py')}
    assert actual == _EXPECTED_PRODUCTION_FILES


def test_core_has_no_runtime_persistence_connectivity_or_ada_imports() -> None:
    forbidden = (
        'ada_command_center.alarms.persistence',
        'ada_command_center.processes',
        'atlanticus',
    )
    for path in sorted(_PRODUCTION_ROOT.glob('*.py')):
        for name in _import_names(path):
            assert not any(name.startswith(prefix) for prefix in forbidden)
            assert name != 'ada'
            assert not name.startswith('ada.')


def test_production_code_has_no_comments() -> None:
    for path in sorted(_PRODUCTION_ROOT.glob('*.py')):
        for line in path.read_text(encoding='utf-8').splitlines():
            assert not line.lstrip().startswith('#')
