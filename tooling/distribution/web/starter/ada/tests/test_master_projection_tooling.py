from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_tool(monkeypatch, root, *, synchronized=True):
    project = ModuleType('project')

    class ProjectError(RuntimeError):
        pass

    project.ProjectError = ProjectError
    project._check_environment = lambda _root: None
    project._locked = lambda _root: None
    project._python = lambda _root: root / '.venv/bin/python'
    project._root = lambda: root
    monkeypatch.setitem(sys.modules, 'project', project)
    if synchronized:
        interpreter = root / '.venv/bin/python'
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
    source = Path(__file__).resolve().parents[1] / 'tooling/master_projection.py'
    spec = importlib.util.spec_from_file_location('master_projection_tooling_under_test', source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tooling_uses_the_distributed_runtime_without_password_arguments(
    tmp_path, monkeypatch,
):
    tooling = _load_tool(monkeypatch, tmp_path)
    recorded = []

    def execute(arguments, **kwargs):
        recorded.append((arguments, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tooling.subprocess, 'run', execute)
    assert tooling.main([
        'generate', '--application', 'example', '--environment', 'production',
        '--user', 'master-service', '--output', '/private/master-projection.zip',
    ]) == 0
    arguments, details = recorded[0]
    assert arguments[:3] == [
        str(tmp_path / '.venv/bin/python'), '-m',
        'application.master_projection.material',
    ]
    assert '--password' not in arguments
    assert details['cwd'] == tmp_path


def test_tooling_refuses_to_run_without_project_sync(tmp_path, monkeypatch):
    tooling = _load_tool(monkeypatch, tmp_path, synchronized=False)
    assert tooling.main(['generate']) == 2
