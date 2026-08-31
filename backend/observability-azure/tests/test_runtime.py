from atlanticus.observability import (
    EventAudience,
    EventCategory,
    EventSeverity,
    ObservabilityEvent,
    ObservabilitySettings,
)
from atlanticus.observability_azure import (
    AzureObservabilityRuntime,
    build_azure_export_runtime,
    build_azure_observability_runtime,
)


class _Backend:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.closed = 0

    def emit(self, payload: dict[str, object], _severity: EventSeverity) -> None:
        self.payloads.append(payload)

    def close(self) -> None:
        self.closed += 1


def _settings() -> ObservabilitySettings:
    return ObservabilitySettings.build(
        application='ada-test',
        service='web',
        component='web',
        environment='local',
    )


def test_export_runtime_without_connection_string_is_noop() -> None:
    runtime = build_azure_export_runtime(
        observability_settings=_settings(),
        connection_string=None,
    )
    assert isinstance(runtime, AzureObservabilityRuntime)
    assert runtime.emit(
        ObservabilityEvent(
            name='web.callback.failed',
            category=EventCategory.DIAGNOSTIC,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.ERROR,
        )
    )
    runtime.close()
    runtime.close()
    assert runtime.closed


def test_runtime_owns_single_backend_and_filters_info() -> None:
    backend = _Backend()
    runtime = build_azure_observability_runtime(
        observability_settings=_settings(),
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
            'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=abc',
        },
        backend_factory=lambda _azure, _obs: backend,
    )
    assert runtime.emit(
        ObservabilityEvent(
            name='dependency.ok',
            category=EventCategory.DEPENDENCY,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.INFO,
        )
    )
    assert runtime.emit(
        ObservabilityEvent(
            name='dependency.failed',
            category=EventCategory.DEPENDENCY,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.ERROR,
        )
    )
    assert len(backend.payloads) == 1
    runtime.close()
    runtime.close()
    assert backend.closed == 1
    assert not runtime.emit(
        ObservabilityEvent(
            name='dependency.failed.again',
            category=EventCategory.DEPENDENCY,
            severity=EventSeverity.ERROR,
        )
    )


def test_file_logs_switch_does_not_disable_azure_export() -> None:
    backend = _Backend()
    settings = ObservabilitySettings.build(
        application='ada-test',
        service='web',
        component='web',
        environment='local',
        file_logs_enabled=False,
    )
    runtime = build_azure_observability_runtime(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
            'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=abc',
        },
        backend_factory=lambda _azure, _obs: backend,
    )

    assert runtime.emit(
        ObservabilityEvent(
            name='web.callback.failed',
            category=EventCategory.DIAGNOSTIC,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.ERROR,
        )
    )
    assert len(backend.payloads) == 1
    runtime.close()
