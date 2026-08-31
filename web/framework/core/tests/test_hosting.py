from types import SimpleNamespace

import pytest

import atlanticus.web.hosting as hosting

_MEMORY_GIB = 1024 * 1024 * 1024


class _Runtime:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = 0

    def server(self, environ, start_response):
        self.calls += 1
        return ('ok', environ, start_response)

    def close(self) -> None:
        self.closed += 1


def test_gunicorn_capacity_is_derived_from_detected_resources(monkeypatch):
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (4.0, 'test_cpu'))
    monkeypatch.setattr(
        hosting,
        '_detect_memory_bytes',
        lambda: (8 * _MEMORY_GIB, 'test_memory'),
    )

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == 3
    assert capacity.threads == 2
    assert capacity.effective_cpu == 4.0
    assert capacity.cpu_source == 'test_cpu'
    assert capacity.memory_bytes == 8 * _MEMORY_GIB
    assert capacity.memory_source == 'test_memory'


def test_gunicorn_capacity_ignores_legacy_environment_overrides(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_WEB_WORKERS', '99')
    monkeypatch.setenv('ATLANTICUS_WEB_THREADS', '99')
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (2.0, 'test_cpu'))
    monkeypatch.setattr(
        hosting,
        '_detect_memory_bytes',
        lambda: (4 * _MEMORY_GIB, 'test_memory'),
    )

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == 2
    assert capacity.threads == 2


def test_gunicorn_capacity_uses_conservative_fallback(monkeypatch):
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (1.0, 'fallback'))
    monkeypatch.setattr(hosting, '_detect_memory_bytes', lambda: (None, 'fallback'))

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == 1
    assert capacity.threads == 1


def test_worker_application_keeps_master_light_and_warms_once():
    created = []

    def factory():
        runtime = _Runtime()
        created.append(runtime)
        return runtime

    application = hosting.WorkerApplication(factory)

    assert created == []
    assert application.warmed_up is False

    application.warmup()
    application.warmup()

    assert len(created) == 1
    assert application.warmed_up is True


def test_worker_application_delegates_wsgi_and_closes_idempotently():
    runtime = _Runtime()
    application = hosting.WorkerApplication(lambda: runtime)
    start_response = object()

    application.warmup()
    result = application({'PATH_INFO': '/'}, start_response)
    application.close()
    application.close()

    assert result == ('ok', {'PATH_INFO': '/'}, start_response)
    assert runtime.calls == 1
    assert runtime.closed == 1
    assert application.warmed_up is False


def test_worker_application_rejects_requests_before_worker_warmup():
    application = hosting.WorkerApplication(_Runtime)

    with pytest.raises(RuntimeError, match='worker runtime is not initialized'):
        application({}, object())


def test_worker_application_does_not_publish_invalid_runtime():
    class InvalidRuntime:
        server = object()

        def close(self):
            return None

    application = hosting.WorkerApplication(InvalidRuntime)

    with pytest.raises(TypeError, match='worker runtime server must be callable'):
        application.warmup()

    assert application.warmed_up is False


def test_gunicorn_warmup_hook_requires_worker_application():
    worker = SimpleNamespace(wsgi=object())

    with pytest.raises(RuntimeError, match='does not support worker warmup'):
        hosting.warmup_gunicorn_worker(worker)


def test_gunicorn_hooks_delegate_to_worker_application():
    runtime = _Runtime()
    application = hosting.WorkerApplication(lambda: runtime)
    worker = SimpleNamespace(wsgi=application)

    hosting.warmup_gunicorn_worker(worker)
    hosting.close_gunicorn_worker(worker)

    assert runtime.closed == 1
    assert application.warmed_up is False


def test_gunicorn_close_hook_is_safe_when_close_is_not_supported():
    worker = SimpleNamespace(wsgi=object())

    hosting.close_gunicorn_worker(worker)
