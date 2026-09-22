import pytest

from ada_command_center.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)

from .support import delivery_configuration, resolution_key, runtime_configuration


def test_ready_resolution_requires_atomic_runtime_and_delivery_artifacts() -> None:
    key = resolution_key()
    resolution = AlarmConfigurationResolution(
        resolution_key=key,
        status=AlarmResolutionStatus.READY,
        findings=(
            AlarmResolutionFinding(
                code='administrative_note',
                severity=AlarmResolutionFindingSeverity.WARNING,
                message='Administrative warning',
            ),
        ),
        runtime_configuration=runtime_configuration(),
        delivery_configuration=delivery_configuration(),
    )
    assert resolution.status is AlarmResolutionStatus.READY

    with pytest.raises(ValueError, match='requires Runtime and Delivery'):
        AlarmConfigurationResolution(
            resolution_key=key,
            status=AlarmResolutionStatus.READY,
            findings=(),
        )


def test_ready_resolution_rejects_blocking_finding() -> None:
    with pytest.raises(ValueError, match='must not contain BLOCKING'):
        AlarmConfigurationResolution(
            resolution_key=resolution_key(),
            status=AlarmResolutionStatus.READY,
            findings=(
                AlarmResolutionFinding(
                    code='missing_tool',
                    severity=AlarmResolutionFindingSeverity.BLOCKING,
                    message='Tool is missing',
                ),
            ),
            runtime_configuration=runtime_configuration(),
            delivery_configuration=delivery_configuration(),
        )


def test_blocked_resolution_requires_blocking_finding_and_no_artifacts() -> None:
    blocked = AlarmConfigurationResolution(
        resolution_key=resolution_key(),
        status=AlarmResolutionStatus.BLOCKED,
        findings=(
            AlarmResolutionFinding(
                code='missing_tool',
                severity=AlarmResolutionFindingSeverity.BLOCKING,
                message='Tool is missing',
                reference_key='process-sag',
            ),
        ),
    )
    assert blocked.runtime_configuration is None
    assert blocked.delivery_configuration is None

    with pytest.raises(ValueError, match='at least one BLOCKING'):
        AlarmConfigurationResolution(
            resolution_key=resolution_key(),
            status=AlarmResolutionStatus.BLOCKED,
            findings=(),
        )

    with pytest.raises(ValueError, match='must not contain materialized'):
        AlarmConfigurationResolution(
            resolution_key=resolution_key(),
            status=AlarmResolutionStatus.BLOCKED,
            findings=(
                AlarmResolutionFinding(
                    code='missing_tool',
                    severity=AlarmResolutionFindingSeverity.BLOCKING,
                    message='Tool is missing',
                ),
            ),
            runtime_configuration=runtime_configuration(),
            delivery_configuration=delivery_configuration(),
        )


def test_ready_resolution_requires_exact_artifact_resolution_keys() -> None:
    key = resolution_key(alarm_revision='R43')
    with pytest.raises(ValueError, match='Runtime configuration resolution_key'):
        AlarmConfigurationResolution(
            resolution_key=key,
            status=AlarmResolutionStatus.READY,
            findings=(),
            runtime_configuration=runtime_configuration(),
            delivery_configuration=delivery_configuration(),
        )
