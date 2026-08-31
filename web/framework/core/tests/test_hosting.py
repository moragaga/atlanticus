import atlanticus.web.hosting as hosting

_MEMORY_GIB = 1024 * 1024 * 1024


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
