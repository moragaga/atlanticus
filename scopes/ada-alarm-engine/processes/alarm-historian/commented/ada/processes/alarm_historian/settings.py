# Espejo pedagógico del código productivo: mismos contratos y ejecución.
from __future__ import annotations

from dataclasses import dataclass

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.runtime.storage import validate_path_segment

RUNTIME_APPLICATION_VARIABLE = 'ALARM_RUNTIME_APPLICATION'
MAX_RECORDS_VARIABLE = 'ALARM_HISTORIAN_MAX_RECORDS'


# Error específico de la configuración del historiador.
class AlarmHistorianSettingsError(ValueError):
    pass


# Datos validados, inmutables y propios del proceso.
@dataclass(frozen=True, slots=True)
class AlarmHistorianSettings:
    stream_id: str
    producer_application: str
    max_records: int

    # Convierte el contrato resuelto en los valores del proceso.
    # La identidad del stream FACTS deriva de la APPLICATION de Runtime.
    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmHistorianSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        try:
            producer = validate_path_segment(
                configuration.require(RUNTIME_APPLICATION_VARIABLE), name='runtime_application'
            )
        except (TypeError, ValueError) as error:
            raise AlarmHistorianSettingsError(str(error)) from error
        value = configuration.require(MAX_RECORDS_VARIABLE)
        if not value.isdecimal() or value.startswith('0'):
            raise AlarmHistorianSettingsError('max_records must be a positive decimal integer')
        count = int(value)
        if not 1 <= count <= 10000:
            raise AlarmHistorianSettingsError('max_records must be between 1 and 10000')
        return cls(stream_id=producer, producer_application=producer, max_records=count)


# Declara las variables que el bootstrap puede consumir.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=RUNTIME_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=MAX_RECORDS_VARIABLE, default='100'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
