from __future__ import annotations

from types import SimpleNamespace

from ada.web.application.generic import host
from ada.web.application.generic.adoption import (
    ToolAdoptingWorkerRuntime,
    ToolRevision,
)
from ada.web.tools.persistence import ToolProjectionResolutionState


class StubServer:
    def __init__(self, name: str):
        self.wsgi_app = lambda _environ, _start: [name.encode()]


class StubWorker:
    def __init__(self, name: str):
        self.application = SimpleNamespace(services=None)
        self.server = StubServer(name)
        self.closed = 0

    def close(self):
        self.closed += 1


def test_startup_mode_keeps_original_worker_and_does_not_check_projection(monkeypatch):
    monkeypatch.setenv('ADA_TOOL_ADOPTION_MODE', 'startup')
    worker = StubWorker('initial')
    monkeypatch.setattr(host, '_create_plain_worker_runtime', lambda **kwargs: worker)
    monkeypatch.setattr(host, '_active_tool_revision', lambda settings: 1 / 0)
    assert host.create_worker_runtime(settings=object()) is worker


def test_on_page_load_enables_worker_replacement(monkeypatch):
    monkeypatch.setenv('ADA_TOOL_ADOPTION_MODE', 'on_page_load')
    created = []
    revision = {'value': None}

    def build(**_kwargs):
        worker = StubWorker(str(len(created)))
        created.append(worker)
        return worker

    monkeypatch.setattr(host, '_create_plain_worker_runtime', build)
    monkeypatch.setattr(
        host,
        '_active_tool_revision',
        lambda settings: ToolRevision(True, revision['value']),
    )
    worker = host.create_worker_runtime(settings=object())
    assert isinstance(worker, ToolAdoptingWorkerRuntime)
    revision['value'] = 'release-b'
    result = worker.server.wsgi_app(
        {'PATH_INFO': '/', 'REQUEST_METHOD': 'GET', 'HTTP_ACCEPT': 'text/html'},
        lambda *_: None,
    )
    assert b''.join(result) == b'1'
    result.close()
    assert created[0].closed == 1
    worker.close()
    assert created[1].closed == 1


def test_ready_projection_revision_comes_from_release_identity(monkeypatch):
    projection = SimpleNamespace(source_release_id=SimpleNamespace(value='release-b'))
    resolution = SimpleNamespace(
        state=ToolProjectionResolutionState.READY,
        projection=projection,
    )
    monkeypatch.setattr(host, '_resolve_tool_projection', lambda _settings: resolution)
    assert host._active_tool_revision(object()) == ToolRevision(True, 'release-b')
    resolution.state = ToolProjectionResolutionState.INVALID
    assert host._active_tool_revision(object()) == ToolRevision(False, None)
    resolution.state = ToolProjectionResolutionState.UNCONFIGURED
    assert host._active_tool_revision(object()) == ToolRevision(True, None)
