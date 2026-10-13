from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.generic.adoption import (
    ADOPTION_MODE_VARIABLE,
    ToolAdoptingWorkerRuntime,
    ToolAdoptionMode,
    ToolRevision,
)


class Server:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self.wsgi_app = self.respond

    def respond(self, _environ, start_response):
        self.calls += 1
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [self.name.encode()]


class Worker:
    def __init__(self, name: str) -> None:
        self.server = Server(name)
        self.application = SimpleNamespace(services=Services(), server=self.server)
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class Services:
    def __init__(self) -> None:
        self.stopped = []

    def contains(self, key):
        return key == 'ada.kpi.collector.runtime'

    def require(self, key):
        return SimpleNamespace(stop=lambda: self.stopped.append(key))


class Reader:
    def __init__(self, revision=None) -> None:
        self.current = revision
        self.reads = 0
        self.fail = False
        self.on_read = None

    def __call__(self):
        self.reads += 1
        if self.fail:
            raise OSError('Cosmos unavailable')
        if self.on_read is not None:
            return self.on_read(self.reads)
        return ToolRevision(True, self.current)


class Factory:
    def __init__(self) -> None:
        self.created = []
        self.fail = False

    def __call__(self):
        if self.fail:
            raise ValueError('Invalid Tool')
        worker = Worker(f'revision-{len(self.created) + 1}')
        self.created.append(worker)
        return worker


def make_app(reader=None, factory=None):
    reader = reader or Reader()
    factory = factory or Factory()
    first = Worker('initial')
    adoption = ToolAdoptingWorkerRuntime(
        initial=first,
        revision_reader=reader,
        worker_factory=factory,
    )
    return adoption, first, reader, factory


def request(app, path='/', *, accept='text/html', method='GET', finish=True):
    response = app.server.wsgi_app(
        {'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ACCEPT': accept},
        lambda *_args: None,
    )
    if finish:
        try:
            return b''.join(response)
        finally:
            response.close()
    return response


def test_initial_unconfigured_adopts_first_projection_by_f5():
    app, initial, reader, factory = make_app()
    assert request(app) == b'initial'
    reader.current = 'release-b'
    assert request(app) == b'revision-1'
    assert app.active_revision.release_id == 'release-b'
    assert initial.closed == 1
    assert initial.application.services.stopped == ['ada.kpi.collector.runtime']
    assert len(factory.created) == 1
    app.close()
    assert factory.created[0].closed == 1


def test_repeated_f5_on_same_revision_does_not_rebuild():
    reader = Reader('release-a')
    app, first, _, factory = make_app(reader)
    for _ in range(5):
        assert request(app) == b'initial'
    assert factory.created == []
    assert reader.reads == 6
    assert first.closed == 0
    app.close()


def test_non_page_requests_do_not_query_cosmos_or_adopt():
    app, first, reader, factory = make_app()
    reader.current = 'release-b'
    for path in ('/_dash-layout', '/_dash-dependencies', '/assets/a.css', '/health/live', '/api/x'):
        assert request(app, path) == b'initial'
    assert request(app, method='POST') == b'initial'
    assert request(app, accept='application/json') == b'initial'
    assert reader.reads == 1
    assert factory.created == []
    assert first.closed == 0
    app.close()


def test_invalid_projection_does_not_replace_active_runtime():
    app, initial, reader, factory = make_app()
    reader.on_read = lambda n: ToolRevision(n == 1, 'release-b' if n == 1 else None)
    assert request(app) == b'initial'
    assert factory.created == []
    assert initial.closed == 0
    app.close()


def test_failed_build_retains_prior_and_can_retry():
    app, initial, reader, factory = make_app()
    reader.current = 'release-b'
    factory.fail = True
    assert request(app) == b'initial'
    assert initial.closed == 0
    factory.fail = False
    assert request(app) == b'revision-1'
    assert initial.closed == 1
    app.close()


def test_failed_revision_lookup_retains_existing():
    app, initial, reader, _ = make_app()
    reader.fail = True
    assert request(app) == b'initial'
    assert initial.closed == 0
    app.close()


def test_candidate_is_discarded_if_projection_changes_during_build():
    app, first, reader, factory = make_app()
    reader.on_read = lambda n: ToolRevision(True, 'release-a' if n == 2 else 'release-b')
    assert request(app) == b'initial'
    assert len(factory.created) == 1
    assert factory.created[0].closed == 1
    assert first.closed == 0
    app.close()


def test_retired_runtime_is_closed_after_inflight_response():
    app, initial, reader, factory = make_app()
    inflight = request(app, finish=False)
    reader.current = 'release-b'
    assert request(app) == b'revision-1'
    assert initial.closed == 0
    assert b''.join(inflight) == b'initial'
    inflight.close()
    inflight.close()
    assert initial.closed == 1
    assert factory.created[0].closed == 0
    app.close()
    assert factory.created[0].closed == 1


def test_close_is_idempotent_and_rejects_new_requests():
    app, initial, _, _ = make_app()
    app.close()
    app.close()
    assert initial.closed == 1
    with pytest.raises(RuntimeError, match='closed'):
        request(app, accept='application/json')


def test_releases_worker_even_if_wsgi_dispatch_fails():
    initial = Worker('initial')

    def broken_wsgi(_environ, _start):
        raise OSError('bad')

    initial.server.wsgi_app = broken_wsgi
    reader = Reader()
    factory = Factory()
    app = ToolAdoptingWorkerRuntime(
        initial=initial,
        revision_reader=reader,
        worker_factory=factory,
    )
    with pytest.raises(OSError):
        request(app, accept='application/json')
    reader.current = 'release-b'
    assert request(app) == b'revision-1'
    assert initial.closed == 1
    app.close()


def test_mode_is_explicit_and_off_by_default():
    assert ADOPTION_MODE_VARIABLE == 'ADA_TOOL_ADOPTION_MODE'
    assert ToolAdoptionMode('startup') is ToolAdoptionMode.STARTUP
    assert ToolAdoptionMode('on_page_load') is ToolAdoptionMode.ON_PAGE_LOAD
    with pytest.raises(ValueError):
        ToolAdoptionMode('polling')


def test_mode_can_be_enabled_from_dotenv(tmp_path, monkeypatch):
    from ada.web.application.generic.adoption import ToolAdoptionSettings

    monkeypatch.delenv(ADOPTION_MODE_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    assert ToolAdoptionSettings().mode is ToolAdoptionMode.STARTUP
    (tmp_path / '.env').write_text('ADA_TOOL_ADOPTION_MODE=on_page_load\n', encoding='utf-8')
    assert ToolAdoptionSettings().mode is ToolAdoptionMode.ON_PAGE_LOAD
    monkeypatch.setenv(ADOPTION_MODE_VARIABLE, 'startup')
    assert ToolAdoptionSettings().mode is ToolAdoptionMode.STARTUP


def test_invalid_mode_in_configuration_is_rejected(tmp_path, monkeypatch):
    from pydantic import ValidationError

    from ada.web.application.generic.adoption import ToolAdoptionSettings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(ADOPTION_MODE_VARIABLE, 'always_on')
    with pytest.raises(ValidationError):
        ToolAdoptionSettings()


def test_navigation_to_manager_also_adopts_projection():
    app, _first, reader, _factory = make_app()
    reader.current = 'release-b'
    assert request(app, '/manager/tools') == b'revision-1'
    app.close()


def test_unconfigured_revision_replaces_prior_tool():
    reader = Reader('release-a')
    app, first, _, factory = make_app(reader)
    reader.current = None
    assert request(app) == b'revision-1'
    assert app.active_revision == ToolRevision(True, None)
    assert first.closed == 1
    app.close()
