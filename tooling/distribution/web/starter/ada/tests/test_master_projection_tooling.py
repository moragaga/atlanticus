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


def test_tooling_uses_automatic_provisioner_without_location_arguments(tmp_path, monkeypatch):
    tooling = _load_tool(monkeypatch, tmp_path)
    recorded = []

    def execute(arguments, **kwargs):
        recorded.append((arguments, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tooling.subprocess, 'run', execute)
    assert tooling.main(['generate', '--user', 'master-service']) == 0
    arguments, details = recorded[0]
    assert arguments == [
        str(tmp_path / '.venv/bin/python'), '-m',
        'application.master_projection.provision',
        'generate', '--user', 'master-service',
    ]
    assert '--output' not in arguments
    assert '--application' not in arguments
    assert '--environment' not in arguments
    assert '--password' not in arguments
    assert details['cwd'] == tmp_path


def test_tooling_refuses_to_run_without_project_sync(tmp_path, monkeypatch):
    tooling = _load_tool(monkeypatch, tmp_path, synchronized=False)
    assert tooling.main(['generate', '--user', 'master-service']) == 2


def test_master_projection_tooling_has_portable_launchers() -> None:
    root = Path(__file__).resolve().parents[1] / 'tooling'
    shell = (root / 'master_projection.sh').read_text(encoding='utf-8')
    windows = (root / 'master_projection.cmd').read_text(encoding='utf-8')
    assert 'uv run --python 3.14.2' in shell
    assert 'uv run --python 3.14.2' in windows
    assert 'master_projection.py' in shell
    assert 'master_projection.py' in windows
