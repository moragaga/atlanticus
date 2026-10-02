from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORT_PREFIXES = (
    'ada.data',
    'ada.web',
    'atlanticus.data_producers',
)
FORBIDDEN_CALLS = {'sleep'}
FORBIDDEN_NAMES = {'AlarmScheduler', 'LeaseManager', 'ProcessLoop'}


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'src'


def test_runtime_does_not_import_retired_or_upstream_implementation_owners() -> None:
    for path in _source_root().rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names = (node.module or '',)
            else:
                continue
            for name in names:
                assert not name.startswith(FORBIDDEN_IMPORT_PREFIXES), (path, name)


def test_runtime_does_not_own_loop_sleep_or_lease_implementation() -> None:
    for path in _source_root().rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.While), path
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in FORBIDDEN_CALLS, path
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in FORBIDDEN_CALLS, path
            if isinstance(node, ast.ClassDef):
                assert node.name not in FORBIDDEN_NAMES, path
