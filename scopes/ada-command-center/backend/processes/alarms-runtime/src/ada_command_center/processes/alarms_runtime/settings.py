from __future__ import annotations

import math
from dataclasses import dataclass

from ada_command_center.alarms.core import EvidenceContractRef
from ada_command_center.domain.alarms.identity import ALARM_CONFIGURATION_SOURCE_KEY
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration


class AlarmRuntimeSettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmRuntimeSettings:
    pi_source: str
    pi_application: str
    dispatch_application: str | None
    blockgrade_application: str | None
    remanentes_application: str | None
    fabrica_planes_application: str | None
    technical_evidence_contract: EvidenceContractRef
    poll_interval_seconds: float

    @property
    def source_key(self) -> str:
        return ALARM_CONFIGURATION_SOURCE_KEY

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmRuntimeSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be ResolvedConfiguration')
        return cls(
            pi_source=_pi_source(configuration.require('PI_SOURCE')),
            pi_application=_required(configuration.require('PI_APPLICATION'), 'PI_APPLICATION'),
            dispatch_application=_optional_application(
                configuration.get('DISPATCH_APPLICATION'), 'DISPATCH_APPLICATION'
            ),
            blockgrade_application=_optional_application(
                configuration.get('BLOCKGRADE_APPLICATION'), 'BLOCKGRADE_APPLICATION'
            ),
            remanentes_application=_optional_application(
                configuration.get('REMANENTES_APPLICATION'), 'REMANENTES_APPLICATION'
            ),
            fabrica_planes_application=_optional_application(
                configuration.get('FABRICA_PLANES_APPLICATION'), 'FABRICA_PLANES_APPLICATION'
            ),
            technical_evidence_contract=EvidenceContractRef(
                contract_key=_required(
                    configuration.require('ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY'),
                    'ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY',
                ),
                contract_version=_required(
                    configuration.require('ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION'),
                    'ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION',
                ),
            ),
            poll_interval_seconds=_poll_interval(
                configuration.require('ALARM_RUNTIME_POLL_SECONDS')
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='PI_SOURCE'),
        ConfigurationVariableSpec(key='PI_APPLICATION'),
        ConfigurationVariableSpec(key='DISPATCH_APPLICATION', required=False),
        ConfigurationVariableSpec(key='BLOCKGRADE_APPLICATION', required=False),
        ConfigurationVariableSpec(key='REMANENTES_APPLICATION', required=False),
        ConfigurationVariableSpec(key='FABRICA_PLANES_APPLICATION', required=False),
        ConfigurationVariableSpec(key='ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY'),
        ConfigurationVariableSpec(key='ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION'),
        ConfigurationVariableSpec(key='ALARM_RUNTIME_POLL_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AlarmRuntimeSettingsError(
            f'{name} must be non-empty text without surrounding whitespace'
        )
    return value


def _optional_application(value: str | None, name: str) -> str | None:
    if value is None or value == '':
        return None
    return _required(value, name)


def _pi_source(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise AlarmRuntimeSettingsError('PI_SOURCE must be NOTPII or PI_WEB_API')
    normalized = value.lower()
    if normalized not in {'notpii', 'pi_web_api'}:
        raise AlarmRuntimeSettingsError('PI_SOURCE must be NOTPII or PI_WEB_API')
    return normalized


def _poll_interval(value: str) -> float:
    try:
        interval = float(value)
    except (TypeError, ValueError) as error:
        raise AlarmRuntimeSettingsError(
            'ALARM_RUNTIME_POLL_SECONDS must be a positive number'
        ) from error
    if not math.isfinite(interval) or interval <= 0:
        raise AlarmRuntimeSettingsError('ALARM_RUNTIME_POLL_SECONDS must be a positive number')
    return interval
