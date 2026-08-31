from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import Lock

from atlanticus.kernel import DataSanitizer
from atlanticus.observability import Observability, ObservabilityEvent, ObservabilitySettings
from atlanticus.observability_azure.bootstrap import (
    AzureLogBackendFactory,
    build_azure_observability_extension,
)


class AzureObservabilityRuntime:
    def __init__(self, observability: Observability) -> None:
        if not isinstance(observability, Observability):
            raise TypeError('observability must be an Observability')
        self._observability = observability
        self._lock = Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def emit(self, event: ObservabilityEvent) -> bool:
        if not isinstance(event, ObservabilityEvent):
            raise TypeError('event must be an ObservabilityEvent')
        with self._lock:
            if self._closed:
                return False
        try:
            self._observability.emit(event)
        except Exception:
            return False
        return True

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._observability.close()


def build_azure_observability_runtime(
    *,
    observability_settings: ObservabilitySettings,
    environ: Mapping[str, str],
    volume_path: str | Path | None = None,
    backend_factory: AzureLogBackendFactory | None = None,
) -> AzureObservabilityRuntime:
    extension = build_azure_observability_extension(
        observability_settings=observability_settings,
        environ=environ,
        volume_path=volume_path,
        backend_factory=backend_factory,
    )
    return AzureObservabilityRuntime(
        Observability(
            settings=observability_settings,
            sink=extension.sink,
            sanitizer=DataSanitizer(),
            trace_bridge=extension.trace_bridge,
        )
    )


def build_azure_export_runtime(
    *,
    observability_settings: ObservabilitySettings,
    connection_string: str | None,
    backend_factory: AzureLogBackendFactory | None = None,
) -> AzureObservabilityRuntime:
    if connection_string is not None and not isinstance(connection_string, str):
        raise TypeError('connection_string must be a string or None')
    normalized = connection_string.strip() if isinstance(connection_string, str) else None
    environ = {
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export' if normalized else 'off',
        'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
    }
    if normalized:
        environ['APPLICATION_INSIGHTS_CONNECTION_STRING'] = normalized
    return build_azure_observability_runtime(
        observability_settings=observability_settings,
        environ=environ,
        backend_factory=backend_factory,
    )
