from __future__ import annotations

import pytest

from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.observability import WebEvent, WebSeverity
from atlanticus.web.observability_azure import create_web_azure_event_sink


class _Backend:
    def __init__(self):
        self.events = []

    def emit(self, payload, severity):
        self.events.append((payload, severity))

    def close(self):
        pass


def _sink(backend):
    return create_web_azure_event_sink(
        application='web-test',
        mode='export',
        profile='slim',
        environment=WebEnvironment.PRODUCTION,
        connection_string='InstrumentationKey=test',
        backend_factory=lambda **kwargs: backend,
    )


def test_slow_request_export_has_duration_and_allowlisted_request_kind_only():
    backend = _Backend()
    sink = _sink(backend)
    sink.emit(WebEvent(
        name='web.request.slow', severity=WebSeverity.WARNING,
        message='PRIVATE', application='web-test',
        context={
            'duration_ms': 2345.1258, 'request_kind': 'dash_callback',
            'method': 'POST', 'status_code': 200,
            'path': '/private/secret', 'user_id': 'hidden', 'token': 'hidden',
        },
    ))
    payload, severity = backend.events[0]
    assert severity.value == 'warning'
    assert payload['duration_ms'] == 2345.126
    assert payload['request_kind'] == 'dash_callback'
    assert payload['http_method'] == 'POST'
    assert payload['http_status_code'] == 200
    assert 'PRIVATE' not in str(payload)
    assert 'private' not in str(payload)
    assert 'hidden' not in str(payload)
    sink.close()


@pytest.mark.parametrize('duration,kind', [
    (float('nan'), 'secret'), (float('inf'), 'secret'), (-1, 'secret'),
    (True, 'secret'), ('1000', 'secret'),
])
def test_untrusted_slow_context_is_rejected(duration, kind):
    backend = _Backend()
    sink = _sink(backend)
    sink.emit(WebEvent(
        name='web.request.slow', severity=WebSeverity.WARNING,
        message='internal', application='web-test',
        context={'duration_ms': duration, 'request_kind': kind},
    ))
    payload = backend.events[0][0]
    assert 'duration_ms' not in payload
    assert 'request_kind' not in payload
    sink.close()


def test_other_events_do_not_inherit_duration_metadata():
    backend = _Backend()
    sink = _sink(backend)
    sink.emit(WebEvent(
        name='web.request.failed', severity=WebSeverity.ERROR,
        message='internal', application='web-test',
        context={'duration_ms': 99999, 'request_kind': 'dash_callback'},
    ))
    payload = backend.events[0][0]
    assert 'duration_ms' not in payload
    assert 'request_kind' not in payload
    sink.close()
