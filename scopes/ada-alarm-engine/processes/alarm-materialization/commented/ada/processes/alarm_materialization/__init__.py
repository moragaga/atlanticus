# Superficie pública mínima del proceso durante el incremento de acquisition read-only.
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationAcquisitionError,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationContractError,
)
from ada.processes.alarm_materialization.repository import (
    AlarmConfigurationReader,
    CosmosAlarmConfigurationRepository,
    CosmosAlarmConfigurationRepositorySettings,
)

__version__ = '1.0.0'

__all__ = [
    'AlarmConfigurationReader',
    'AlarmMaterializationAcquisitionError',
    'AlarmMaterializationCandidate',
    'AlarmMaterializationConfigurationPending',
    'AlarmMaterializationContractError',
    'CosmosAlarmConfigurationRepository',
    'CosmosAlarmConfigurationRepositorySettings',
    '__version__',
]
