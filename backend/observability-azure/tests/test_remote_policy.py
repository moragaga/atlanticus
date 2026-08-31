from atlanticus.kernel import DataSanitizer, OperationStatus
from atlanticus.observability import (
    EventAudience,
    EventCategory,
    EventSeverity,
    ObservabilityEvent,
    ObservabilitySettings,
)
from atlanticus.observability_azure import AzureProblemEventProjection


def _settings() -> ObservabilitySettings:
    return ObservabilitySettings.build(
        application='ada',
        service='web',
        environment='dev',
        instance_id='worker-1',
        process_id=10,
    )


def _project(event: ObservabilityEvent):
    payload = event.to_dict(settings=_settings(), sanitizer=DataSanitizer())
    return AzureProblemEventProjection().project(event, payload)


def test_remote_projection_drops_successful_operational_events() -> None:
    event = ObservabilityEvent(
        name='runtime.execution.summary',
        category=EventCategory.LIFECYCLE,
        audience=EventAudience.OPERATIONS,
        severity=EventSeverity.INFO,
        status=OperationStatus.SUCCESS,
    )

    assert _project(event) is None


def test_remote_projection_keeps_warning_error_and_critical() -> None:
    for severity in (EventSeverity.WARNING, EventSeverity.ERROR, EventSeverity.CRITICAL):
        event = ObservabilityEvent(
            name='web.callback.failed',
            category=EventCategory.DIAGNOSTIC,
            audience=EventAudience.OPERATIONS,
            severity=severity,
        )
        projected = _project(event)
        assert projected is not None
        assert projected['level'] == severity.value


def test_remote_projection_keeps_dependency_warning_when_operationally_named() -> None:
    event = ObservabilityEvent(
        name='dependency.slow',
        category=EventCategory.DEPENDENCY,
        audience=EventAudience.OPERATIONS,
        severity=EventSeverity.WARNING,
        attributes={'target_alias': 'pi-primary'},
    )

    projected = _project(event)

    assert projected is not None
    assert projected['event'] == 'dependency.slow'
    assert projected['target_alias'] == 'pi-primary'
