import pytest

from ada.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)

from .support import (
    delivery_configuration,
    engine_configuration,
    modeler_configuration,
    resolution_key,
)


def test_ready_resolution_requires_three_atomic_configurations() -> None:
    resolution = AlarmConfigurationResolution(
        resolution_key=resolution_key(),
        status=AlarmResolutionStatus.READY,
        findings=(),
        engine_configuration=engine_configuration(),
        modeler_configuration=modeler_configuration(),
        delivery_configuration=delivery_configuration(),
    )
    assert resolution.status is AlarmResolutionStatus.READY

    with pytest.raises(ValueError, match='Engine, Modeler, and Delivery'):
        AlarmConfigurationResolution(
            resolution_key=resolution_key(),
            status=AlarmResolutionStatus.READY,
            findings=(),
        )


def test_blocked_resolution_has_no_materialized_configurations() -> None:
    resolution = AlarmConfigurationResolution(
        resolution_key=resolution_key(),
        status=AlarmResolutionStatus.BLOCKED,
        findings=(
            AlarmResolutionFinding(
                code='missing_tool',
                severity=AlarmResolutionFindingSeverity.BLOCKING,
                message='Tool is missing',
            ),
        ),
    )
    assert resolution.engine_configuration is None
    assert resolution.modeler_configuration is None
    assert resolution.delivery_configuration is None
