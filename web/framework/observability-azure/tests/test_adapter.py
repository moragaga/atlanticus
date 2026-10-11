from __future__ import annotations

import logging

import pytest
from flask import Flask

from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.observability import WebErrorInfo, WebEvent, WebObservability, WebSeverity
from atlanticus.web.observability_azure import create_web_azure_event_sink


class _Backend:
    def __init__(self) -> None:
        self.events = []
        self.close_count = 0

    def emit(self, payload, severity) -> None:
        self.events.append((payload, severity))

    def close(self) -> None:
        self.close_count += 1


def _sink(backend: _Backend, *, application: str = 'first', environment=None):
    return create_web_azure_event_sink(
        application=application,
        mode='export',
        profile='slim',
        environment=environment or WebEnvironment.PRODUCTION,
        connection_string='InstrumentationKey=test',
        backend_factory=lambda **_kwargs: backend,
    )


def _observability(sink):
    logger = logging.getLogger('test.web.azure.export')
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    return WebObservability(
        application='first', logger=logger, json_output=False, external_sink=sink
    )


def test_off_mode_uses_no_exporter_or_secret() -> None:
    assert create_web_azure_event_sink(
        application='first',
        mode='off',
        profile='slim',
        environment=WebEnvironment.LOCAL,
        connection_string=None,
        backend_factory=lambda **_kwargs: pytest.fail('Export backend must remain off'),
    ) is None


@pytest.mark.parametrize('mode,profile,environment,connection_string', [
    ('preview', 'slim', WebEnvironment.PRODUCTION, None),
    ('off', 'diagnostic', WebEnvironment.LOCAL, None),
    ('export', 'slim', 'dev', 'InstrumentationKey=test'),
    ('export', 'slim', 'production', 'InstrumentationKey=test'),
    ('export', 'slim', WebEnvironment.PRODUCTION, None),
])
def test_unsupported_export_configuration_is_rejected(
    mode, profile, environment, connection_string
) -> None:
    with pytest.raises((ValueError, TypeError)):
        create_web_azure_event_sink(
            application='first',
            mode=mode,
            profile=profile,
            environment=environment,
            connection_string=connection_string,
        )


@pytest.mark.parametrize('environment', [WebEnvironment.LOCAL, WebEnvironment.PRODUCTION])
def test_export_contains_only_allowlisted_fields(environment) -> None:
    backend = _Backend()
    sink = _sink(backend, environment=environment)
    sink.emit(WebEvent(
        name='web.request.failed',
        severity=WebSeverity.ERROR,
        message='PASSWORD_SHOULD_NOT_LEAVE',
        application='first',
        context={
            'path': '/private/SECRET',
            'authorization': 'SECRET',
            'method': 'GET',
            'status_code': 500,
            'user_id': 'private-user',
        },
        error=WebErrorInfo(type='RuntimeError', message='SECRET'),
    ))
    assert len(backend.events) == 1
    payload, severity = backend.events[0]
    assert payload == {
        'time': payload['time'],
        'application': 'first',
        'environment': environment.value,
        'service': 'web',
        'event': 'web.request.failed',
        'level': 'error',
        'message': 'Web application event',
        'http_status_code': 500,
        'http_method': 'GET',
        'web_error_type': 'RuntimeError',
    }
    assert severity.value == 'error'
    assert 'SECRET' not in str(payload)
    with pytest.raises(ValueError, match='does not match'):
        sink.emit(WebEvent(
            name='web.request.failed', severity=WebSeverity.ERROR,
            message='error', application='second'
        ))
    sink.close()
    sink.close()
    assert backend.close_count == 1
    sink.emit(WebEvent(
        name='web.request.failed', severity=WebSeverity.ERROR,
        message='error', application='first'
    ))
    assert len(backend.events) == 1


def test_bad_event_names_are_not_exported_as_untrusted_strings() -> None:
    backend = _Backend()
    sink = _sink(backend)
    sink.emit(WebEvent(
        name='web.private/secret=abc',
        severity=WebSeverity.WARNING,
        message='secret',
        application='first',
        context={'method': 'GET?secret', 'status_code': True},
        error=WebErrorInfo(type='Error secret!', message='password'),
    ))
    assert backend.events[0][0]['event'] == 'web.unclassified'
    assert 'http_method' not in backend.events[0][0]
    assert 'http_status_code' not in backend.events[0][0]
    assert 'web_error_type' not in backend.events[0][0]
    sink.close()


def test_flask_unhandled_failure_exports_once_without_exception_message() -> None:
    backend = _Backend()
    sink = _sink(backend)
    app = Flask(__name__)
    app.config['PROPAGATE_EXCEPTIONS'] = False
    _observability(sink).attach_flask(app)

    @app.get('/fail')
    def fail():
        raise RuntimeError('SECRET_CREDENTIAL')

    assert app.test_client().get('/fail').status_code == 500
    assert len(backend.events) == 1
    assert backend.events[0][0]['web_error_type'] == 'RuntimeError'
    assert 'SECRET_CREDENTIAL' not in str(backend.events)
    sink.close()


def test_backend_failure_does_not_change_response() -> None:
    class _BrokenBackend(_Backend):
        def emit(self, payload, severity) -> None:
            raise RuntimeError('export refused')

    backend = _BrokenBackend()
    sink = _sink(backend)
    app = Flask(__name__)
    _observability(sink).attach_flask(app)

    @app.get('/failed')
    def failed():
        return 'failure', 503

    assert app.test_client().get('/failed').status_code == 503
    sink.close()
