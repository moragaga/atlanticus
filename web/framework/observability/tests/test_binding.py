import pytest

from atlanticus.web.observability import (
    WebEvent,
    bind_web_external_sink,
    configure_web_observability,
    get_bound_web_external_sink,
)


class _Sink:
    def __init__(self) -> None:
        self.events: list[WebEvent] = []

    def emit(self, event: WebEvent) -> None:
        self.events.append(event)


def test_bound_sink_is_used_by_default_configuration() -> None:
    sink = _Sink()
    binding = bind_web_external_sink(sink)
    try:
        observability = configure_web_observability(application='test', json_output=False)
        observability.warning('web.callback.warning', 'Callback degraded', path='/')
        assert [event.name for event in sink.events] == ['web.callback.warning']
    finally:
        binding.close()
    assert get_bound_web_external_sink() is None


def test_explicit_sink_overrides_process_binding() -> None:
    default_sink = _Sink()
    explicit_sink = _Sink()
    binding = bind_web_external_sink(default_sink)
    try:
        observability = configure_web_observability(
            application='test',
            json_output=False,
            external_sink=explicit_sink,
        )
        observability.error('web.callback.failed', 'Callback failed')
    finally:
        binding.close()
    assert default_sink.events == []
    assert [event.name for event in explicit_sink.events] == ['web.callback.failed']


def test_only_one_process_sink_can_be_bound() -> None:
    first = bind_web_external_sink(_Sink())
    try:
        with pytest.raises(RuntimeError, match='already bound'):
            bind_web_external_sink(_Sink())
    finally:
        first.close()


def test_binding_close_is_idempotent() -> None:
    binding = bind_web_external_sink(_Sink())
    binding.close()
    binding.close()
    assert get_bound_web_external_sink() is None
