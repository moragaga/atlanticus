# Adaptador opcional que reutiliza exclusivamente el backend de exportación Azure existente.
# Nunca crea un ObservabilitySettings de procesos ni convierte production en prd.
from __future__ import annotations

import math
import re
from collections.abc import Callable
from threading import Lock

from atlanticus.observability import EventSeverity
from atlanticus.observability_azure import AzureLogBackend, OpenTelemetryLogBackend
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.observability import WebEvent

_EVENT_PATTERN = re.compile(r'^web\.[a-z][a-z0-9._-]{0,100}$')
_ERROR_TYPE_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,100}$')
_ALLOWED_HTTP_METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'})
WebAzureBackendFactory = Callable[..., AzureLogBackend]


class WebAzureEventSink:
    def __init__(
        self,
        *,
        application: str,
        environment: WebEnvironment,
        backend: AzureLogBackend,
    ) -> None:
        if not isinstance(application, str) or not application.strip():
            raise ValueError('application must not be empty')
        if not isinstance(environment, WebEnvironment):
            raise TypeError('environment must be WebEnvironment')
        if not callable(getattr(backend, 'emit', None)) or not callable(
            getattr(backend, 'close', None)
        ):
            raise TypeError('backend must implement emit() and close()')
        self._application = application
        self._environment = environment
        self._backend = backend
        self._closed = False
        self._lock = Lock()

    def emit(self, event: WebEvent) -> None:
        if not isinstance(event, WebEvent):
            raise TypeError('event must be WebEvent')
        if event.application != self._application:
            raise ValueError('Web event application does not match the Azure sink application')
        # La allowlist descarta mensajes, rutas dinámicas, body, usuario y atributos externos.
        payload: dict[str, str | int | float] = {
            'time': event.timestamp.isoformat(),
            'application': self._application,
            'environment': self._environment.value,
            'service': 'web',
            'event': (
                event.name if _EVENT_PATTERN.fullmatch(event.name) else 'web.unclassified'
            ),
            'level': event.severity.value,
            'message': 'Web application event',
        }
        status = event.context.get('status_code')
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            payload['http_status_code'] = status
        method = event.context.get('method')
        if isinstance(method, str) and method in _ALLOWED_HTTP_METHODS:
            payload['http_method'] = method
        # Para lentitud sólo se permite duración finita y categoría técnica acotada.
        if event.name == 'web.request.slow':
            duration = event.context.get('duration_ms')
            if (
                isinstance(duration, int | float)
                and not isinstance(duration, bool)
                and math.isfinite(duration)
                and duration >= 0
            ):
                payload['duration_ms'] = round(duration, 3)
            request_kind = event.context.get('request_kind')
            if request_kind in ('http', 'dash_callback'):
                payload['request_kind'] = request_kind
        if event.error is not None and _ERROR_TYPE_PATTERN.fullmatch(event.error.type):
            payload['web_error_type'] = event.error.type
        # El mismo lock protege emisión y cierre del exportador por worker.
        with self._lock:
            if self._closed:
                return
            self._backend.emit(payload, EventSeverity(event.severity.value))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._backend.close()


def create_web_azure_event_sink(
    *,
    application: str,
    mode: str,
    profile: str,
    environment: WebEnvironment,
    connection_string: str | None,
    backend_factory: WebAzureBackendFactory | None = None,
) -> WebAzureEventSink | None:
    if mode not in {'off', 'export'}:
        raise ValueError('Web Azure observability mode must be off or export')
    if profile != 'slim':
        raise ValueError('Web Azure observability profile must be slim')
    if not isinstance(environment, WebEnvironment):
        raise TypeError('environment must be WebEnvironment')
    # En modo off no se instancia el SDK ni se necesita credencial.
    if mode == 'off':
        return None
    if not isinstance(connection_string, str) or not connection_string.strip():
        raise ValueError('APPLICATION_INSIGHTS_CONNECTION_STRING is required for Web Azure export')
    factory = backend_factory or OpenTelemetryLogBackend
    backend = factory(
        connection_string=connection_string,
        application=application,
        service='web',
        flush_timeout_seconds=3.0,
    )
    return WebAzureEventSink(
        application=application,
        environment=environment,
        backend=backend,
    )
