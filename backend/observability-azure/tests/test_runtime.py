from atlanticus.observability import (
    EventAudience,
    EventCategory,
    EventSeverity,
    ObservabilityEvent,
    ObservabilitySettings,
)
from atlanticus.observability_azure import (
    build_azure_export_runtime,
    build_azure_observability_runtime,
)


class _Backend:
    def __init__(self) -> None:
        self.records: list[tuple[dict[str, object], EventSeverity]] = []
        self.closed = 0

    def emit(self, payload: dict[str, object], severity: EventSeverity) -> None:
        self.records.append((payload, severity))

    def close(self) -> None:
        self.closed += 1


def _settings() -> ObservabilitySettings:
    return ObservabilitySettings.build(
        application='ada-test',
        service='web',
        component='web',
        environment='local',
    )


def test_export_runtime_without_connection_string_is_noop_and_closes_idempotently() -> None:
    runtime = build_azure_export_runtime(
        observability_settings=_settings(),
        connection_string=None,
    )

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


def test_runtime_filters_info_exports_problem_severities_and_owns_backend() -> None:
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
            name='runtime.execution.summary',
            category=EventCategory.LIFECYCLE,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.INFO,
        )
    )
    for severity in (EventSeverity.WARNING, EventSeverity.ERROR, EventSeverity.CRITICAL):
        assert runtime.emit(
            ObservabilityEvent(
                name='web.callback.failed',
                category=EventCategory.DIAGNOSTIC,
                audience=EventAudience.OPERATIONS,
                severity=severity,
                attributes={'target_alias': 'pi-primary'},
            )
        )

    assert [severity for _, severity in backend.records] == [
        EventSeverity.WARNING,
        EventSeverity.ERROR,
        EventSeverity.CRITICAL,
    ]
    assert all(payload['target_alias'] == 'pi-primary' for payload, _ in backend.records)

    runtime.close()
    runtime.close()

    assert backend.closed == 1
    assert not runtime.emit(
        ObservabilityEvent(
            name='web.callback.failed.again',
            category=EventCategory.DIAGNOSTIC,
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
    assert len(backend.records) == 1
    runtime.close()
