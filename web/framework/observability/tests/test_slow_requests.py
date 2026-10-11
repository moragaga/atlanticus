from __future__ import annotations

import logging

import pytest
from flask import Flask

from atlanticus.web.observability import WebObservability, observability as observability_module


class _Events:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


def _app(sink, *, threshold: int = 2000):
    logger = logging.getLogger(f'test.web.slow.{id(sink)}')
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    observed = WebObservability(
        application='test',
        logger=logger,
        json_output=False,
        external_sink=sink,
        slow_request_threshold_ms=threshold,
    )
    app = Flask(__name__)
    app.config['PROPAGATE_EXCEPTIONS'] = False
    observed.attach_flask(app)

    @app.get('/operation/<key>')
    def operation(key):
        del key
        return 'ok'

    @app.post('/_dash-update-component')
    def dash_callback():
        return 'ok'

    @app.get('/assets/file.css')
    def assets():
        return 'ok'

    @app.get('/health/ready')
    def health():
        return 'ok'

    @app.get('/error')
    def failed():
        return 'failed', 503

    return app


def _clock(monkeypatch, values: tuple[int, ...]):
    it = iter(values)
    monkeypatch.setattr(observability_module, 'perf_counter_ns', lambda: next(it))


def test_normal_request_and_exact_threshold_remain_silent(monkeypatch) -> None:
    events = _Events()
    app = _app(events)
    _clock(monkeypatch, (0, 1_999_000_000, 0, 2_000_000_000))
    with app.test_client() as client:
        assert client.get('/operation/first').status_code == 200
        assert client.get('/operation/second').status_code == 200
    assert events.events == []


def test_slow_request_emits_one_warning_without_sensitive_data(monkeypatch) -> None:
    events = _Events()
    app = _app(events, threshold=1000)
    _clock(monkeypatch, (0, 1_100_000_000))
    response = app.test_client().get('/operation/SECRET?access_token=PRIVATE')
    assert response.status_code == 200
    assert len(events.events) == 1
    event = events.events[0]
    assert event.name == 'web.request.slow'
    assert event.severity.value == 'warning'
    assert event.context == {
        'method': 'GET',
        'status_code': 200,
        'duration_ms': 1100.0,
        'request_kind': 'http',
    }
    assert 'SECRET' not in str(event)
    assert 'PRIVATE' not in str(event)


def test_dash_callback_is_identified_without_exposing_payload(monkeypatch) -> None:
    events = _Events()
    app = _app(events)
    _clock(monkeypatch, (0, 3_200_000_000))
    response = app.test_client().post('/_dash-update-component', json={'output': 'PRIVATE'})
    assert response.status_code == 200
    assert len(events.events) == 1
    assert events.events[0].context['request_kind'] == 'dash_callback'
    assert 'PRIVATE' not in str(events.events[0])


def test_technical_routes_do_not_generate_slow_events(monkeypatch) -> None:
    events = _Events()
    app = _app(events)
    _clock(monkeypatch, ())
    with app.test_client() as client:
        assert client.get('/assets/file.css').status_code == 200
        assert client.get('/health/ready').status_code == 200
    assert events.events == []


def test_server_error_remains_one_failure_event_even_when_slow(monkeypatch) -> None:
    events = _Events()
    app = _app(events)
    _clock(monkeypatch, (0, 5_000_000_000))
    assert app.test_client().get('/error').status_code == 503
    assert [event.name for event in events.events] == ['web.request.failed']


@pytest.mark.parametrize('threshold', (0, -1, True, '2000', 1.0))
def test_slow_request_policy_rejects_invalid_threshold(threshold) -> None:
    with pytest.raises(ValueError, match='positive integer'):
        _app(_Events(), threshold=threshold)


def test_slow_request_sink_failure_does_not_change_http_response(monkeypatch) -> None:
    class _Failing:
        def emit(self, event) -> None:
            del event
            raise RuntimeError('export unavailable')

    app = _app(_Failing())
    _clock(monkeypatch, (0, 3_000_000_000))
    assert app.test_client().get('/operation/normal').status_code == 200
