from __future__ import annotations

from threading import Lock

from atlanticus.web.observability.ports import WebEventSink

_lock = Lock()
_bound_sink: WebEventSink | None = None


class WebExternalSinkBinding:
    def __init__(self, sink: WebEventSink) -> None:
        self._sink = sink
        self._closed = False
        self._lock = Lock()

    @property
    def sink(self) -> WebEventSink:
        return self._sink

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        _unbind(self._sink)


def bind_web_external_sink(sink: WebEventSink) -> WebExternalSinkBinding:
    if not callable(getattr(sink, 'emit', None)):
        raise TypeError('sink must implement emit()')
    global _bound_sink
    with _lock:
        if _bound_sink is not None:
            raise RuntimeError('A Web external observability sink is already bound')
        _bound_sink = sink
    return WebExternalSinkBinding(sink)


def get_bound_web_external_sink() -> WebEventSink | None:
    with _lock:
        return _bound_sink


def _unbind(sink: WebEventSink) -> None:
    global _bound_sink
    with _lock:
        if _bound_sink is sink:
            _bound_sink = None
