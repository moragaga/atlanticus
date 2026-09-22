from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada_command_center.alarms.core import AlarmResolutionKey
from ada_command_center.alarms.materialization.delivery import DeliveryAlarmConfiguration
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration
from ada_command_center.domain.alarms import AlarmIdentity


class AlarmResolutionStatus(StrEnum):
    READY = 'READY'
    BLOCKED = 'BLOCKED'


class AlarmResolutionFindingSeverity(StrEnum):
    BLOCKING = 'BLOCKING'
    WARNING = 'WARNING'


@dataclass(frozen=True, slots=True)
class AlarmResolutionFinding:
    code: str
    severity: AlarmResolutionFindingSeverity
    message: str
    alarm_identity: AlarmIdentity | None = None
    field_path: str | None = None
    reference_key: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.code, 'code')
        if not isinstance(self.severity, AlarmResolutionFindingSeverity):
            raise TypeError('severity must be an AlarmResolutionFindingSeverity')
        _require_non_empty_string(self.message, 'message')
        if self.alarm_identity is not None and not isinstance(
            self.alarm_identity,
            AlarmIdentity,
        ):
            raise TypeError('alarm_identity must be an AlarmIdentity')
        for field_name in ('field_path', 'reference_key'):
            value = getattr(self, field_name)
            if value is not None:
                _require_non_empty_string(value, field_name)


@dataclass(frozen=True, slots=True)
class AlarmConfigurationResolution:
    resolution_key: AlarmResolutionKey
    status: AlarmResolutionStatus
    findings: tuple[AlarmResolutionFinding, ...]
    runtime_configuration: RuntimeAlarmConfiguration | None = None
    delivery_configuration: DeliveryAlarmConfiguration | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        if not isinstance(self.status, AlarmResolutionStatus):
            raise TypeError('status must be an AlarmResolutionStatus')
        if not isinstance(self.findings, tuple):
            raise TypeError('findings must be a tuple')
        for finding in self.findings:
            if not isinstance(finding, AlarmResolutionFinding):
                raise TypeError('findings must contain AlarmResolutionFinding values')
        if self.runtime_configuration is not None and not isinstance(
            self.runtime_configuration,
            RuntimeAlarmConfiguration,
        ):
            raise TypeError('runtime_configuration must be a RuntimeAlarmConfiguration')
        if self.delivery_configuration is not None and not isinstance(
            self.delivery_configuration,
            DeliveryAlarmConfiguration,
        ):
            raise TypeError('delivery_configuration must be a DeliveryAlarmConfiguration')
        blocking = any(
            finding.severity is AlarmResolutionFindingSeverity.BLOCKING for finding in self.findings
        )
        if self.status is AlarmResolutionStatus.READY:
            if blocking:
                raise ValueError('READY resolution must not contain BLOCKING findings')
            if self.runtime_configuration is None or self.delivery_configuration is None:
                raise ValueError('READY resolution requires Runtime and Delivery configurations')
            if self.runtime_configuration.resolution_key != self.resolution_key:
                raise ValueError('Runtime configuration resolution_key must match resolution')
            if self.delivery_configuration.resolution_key != self.resolution_key:
                raise ValueError('Delivery configuration resolution_key must match resolution')
            return
        if not blocking:
            raise ValueError('BLOCKED resolution requires at least one BLOCKING finding')
        if self.runtime_configuration is not None or self.delivery_configuration is not None:
            raise ValueError('BLOCKED resolution must not contain materialized configurations')


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')
