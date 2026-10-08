# Este módulo preserva el contrato público asociado al incremento de Materialization.
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationAcquisitionError,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationContractError,
    AlarmMaterializationSettingsError,
    AlarmMaterializationSupersededError,
)
from ada.processes.alarm_materialization.job import (
    AlarmMaterializationIterationResult,
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
)


from ada.processes.alarm_materialization.repository import (
    AlarmConfigurationReader,
    CosmosAlarmConfigurationRepository,
)
from ada.processes.alarm_materialization.settings import AlarmMaterializationSettings

__version__ = '1.0.0'

__all__ = [
    'AlarmConfigurationReader',
    'AlarmMaterializationAcquisitionError',
    'AlarmMaterializationCandidate',
    'AlarmMaterializationConfigurationPending',
    'AlarmMaterializationContractError',
    'AlarmMaterializationIterationResult',
    'AlarmMaterializationJob',
    'AlarmMaterializationOutcome',
    'AlarmMaterializationSettings',
    'AlarmMaterializationSettingsError',
    'AlarmMaterializationSupersededError',
    'CosmosAlarmConfigurationRepository',
    '__version__',
]
