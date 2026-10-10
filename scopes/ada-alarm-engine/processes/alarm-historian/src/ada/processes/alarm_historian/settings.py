from __future__ import annotations

from dataclasses import dataclass

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.runtime.storage import validate_path_segment

STREAM_ID_VARIABLE = 'ALARM_HISTORIAN_STREAM_ID'
PRODUCER_APPLICATION_VARIABLE = 'ALARM_HISTORIAN_PRODUCER_APPLICATION'
MAX_RECORDS_VARIABLE = 'ALARM_HISTORIAN_MAX_RECORDS'


class AlarmHistorianSettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmHistorianSettings:
    stream_id: str
    producer_application: str
    max_records: int

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmHistorianSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        stream_id = configuration.require(STREAM_ID_VARIABLE)
        if stream_id != stream_id.strip() or not stream_id:
            raise AlarmHistorianSettingsError('stream_id must be non-empty normalized text')
        try:
            producer = validate_path_segment(
                configuration.require(PRODUCER_APPLICATION_VARIABLE), name='producer_application'
            )
        except (TypeError, ValueError) as error:
            raise AlarmHistorianSettingsError(str(error)) from error
        value = configuration.require(MAX_RECORDS_VARIABLE)
        if not value.isdecimal() or value.startswith('0'):
            raise AlarmHistorianSettingsError('max_records must be a positive decimal integer')
        count = int(value)
        if not 1 <= count <= 10000:
            raise AlarmHistorianSettingsError('max_records must be between 1 and 10000')
        return cls(stream_id=stream_id, producer_application=producer, max_records=count)


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=STREAM_ID_VARIABLE),
        ConfigurationVariableSpec(key=PRODUCER_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=MAX_RECORDS_VARIABLE, default='100'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
