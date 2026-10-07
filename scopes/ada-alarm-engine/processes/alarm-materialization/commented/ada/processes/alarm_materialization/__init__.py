# Superficie pública del proceso de materialización de Alarmas; no expone infraestructura a Engine ni Modeler.
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationAcquisitionError,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationContractError,
    AlarmMaterializationQualificationError,
    AlarmMaterializationSettingsError,
    AlarmMaterializationSupersededError,
)
from ada.processes.alarm_materialization.job import (
    AlarmMaterializationIterationResult,
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
)
from ada.processes.alarm_materialization.qualification import (
    AlarmQualificationEvidence,
    AlarmQualificationProvider,
    JsonFileAlarmQualificationProvider,
)
from ada.processes.alarm_materialization.repository import (
    AlarmConfigurationReader,
    CosmosAlarmConfigurationRepository,
    CosmosAlarmConfigurationRepositorySettings,
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
    'AlarmMaterializationQualificationError',
    'AlarmMaterializationSettings',
    'AlarmMaterializationSettingsError',
    'AlarmMaterializationSupersededError',
    'AlarmQualificationEvidence',
    'AlarmQualificationProvider',
    'CosmosAlarmConfigurationRepository',
    'CosmosAlarmConfigurationRepositorySettings',
    'JsonFileAlarmQualificationProvider',
    '__version__',
]
