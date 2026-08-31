import logging

import pytest

from atlanticus.web.observability import WebObservability


class _CollectingSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


class _FailingSink:
    def emit(self, event) -> None:
        del event
        raise RuntimeError('export failed')


def _logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    return logger


def test_external_sink_receives_the_same_sanitized_web_event() -> None:
    sink = _CollectingSink()
    observability = WebObservability(
        application='test',
        logger=_logger('test.web.external'),
        json_output=False,
        external_sink=sink,
    )

    observability.warning('web.callback.warning', 'Callback degraded', token='secret', path='/')

    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.name == 'web.callback.warning'
    assert event.context == {'token': '[REDACTED]', 'path': '/'}


def test_external_sink_failure_never_breaks_web_flow(caplog) -> None:
    logger = logging.getLogger('test.web.external.failure')
    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.WARNING)
    observability = WebObservability(
        application='test',
        logger=logger,
        json_output=False,
        external_sink=_FailingSink(),
    )

    with caplog.at_level(logging.ERROR):
        observability.error('web.callback.failed', 'Callback failed')

    messages = [record.getMessage() for record in caplog.records]
    assert any('event=web.callback.failed' in message for message in messages)
    assert any('event=web.observability.external_sink.failed' in message for message in messages)


def test_external_sink_must_implement_emit() -> None:
    with pytest.raises(TypeError, match='external_sink must implement emit'):
        WebObservability(
            application='test',
            logger=_logger('test.web.external.invalid'),
            json_output=False,
            external_sink=object(),
        )
