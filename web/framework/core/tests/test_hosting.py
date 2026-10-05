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


@pytest.mark.parametrize(
    ('effective_cpu', 'memory_gib', 'expected_workers'),
    [
        (1.0, 1.75, 1),
        (2.0, 3.5, 2),
        (4.0, 7.0, 4),
        (1.0, 4.0, 1),
        (2.0, 8.0, 2),
        (4.0, 16.0, 4),
        (8.0, 32.0, 8),
    ],
)
def test_gunicorn_capacity_uses_effective_cpu_for_supported_profiles(
    monkeypatch,
    effective_cpu,
    memory_gib,
    expected_workers,
):
    memory_bytes = int(memory_gib * _MEMORY_GIB)
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (effective_cpu, 'test_cpu'))
    monkeypatch.setattr(
        hosting,
        '_detect_memory_bytes',
        lambda: (memory_bytes, 'test_memory'),
    )

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == expected_workers
    assert capacity.threads == 2
    assert capacity.effective_cpu == effective_cpu
    assert capacity.cpu_source == 'test_cpu'
    assert capacity.memory_bytes == memory_bytes
    assert capacity.memory_source == 'test_memory'


@pytest.mark.parametrize(
    ('effective_cpu', 'expected_workers'),
    [
        (1.0, 1),
        (1.9, 1),
        (2.9, 2),
        (8.0, 8),
        (12.0, 8),
        (16.0, 8),
    ],
)
def test_gunicorn_capacity_floors_cpu_and_caps_workers_at_eight(
    monkeypatch,
    effective_cpu,
    expected_workers,
):
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (effective_cpu, 'test_cpu'))
    monkeypatch.setattr(hosting, '_detect_memory_bytes', lambda: (None, 'fallback'))

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == expected_workers
    assert capacity.threads == 2


def test_gunicorn_capacity_keeps_memory_as_diagnostic_only(monkeypatch):
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (4.0, 'test_cpu'))

    for memory_bytes in (None, 2 * _MEMORY_GIB, 7 * _MEMORY_GIB, 32 * _MEMORY_GIB):
        monkeypatch.setattr(
            hosting,
            '_detect_memory_bytes',
            lambda memory_bytes=memory_bytes: (memory_bytes, 'test_memory'),
        )

        capacity = hosting.resolve_gunicorn_capacity()

        assert capacity.workers == 4
        assert capacity.threads == 2
        assert capacity.memory_bytes == memory_bytes


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


def test_gunicorn_capacity_uses_conservative_cpu_fallback(monkeypatch):
    monkeypatch.setattr(hosting, '_detect_cpu', lambda: (1.0, 'fallback'))
    monkeypatch.setattr(hosting, '_detect_memory_bytes', lambda: (None, 'fallback'))

    capacity = hosting.resolve_gunicorn_capacity()

    assert capacity.workers == 1
    assert capacity.threads == 2


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
