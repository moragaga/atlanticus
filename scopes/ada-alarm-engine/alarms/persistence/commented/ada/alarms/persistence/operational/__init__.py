# Espejo pedagógico del módulo operacional __init__.py.
# Mantiene la lógica y los contratos del archivo productivo correspondiente.
from ada.alarms.persistence.operational.configuration_adoption import (
    CONFIGURATION_ADOPTION_RECORD_SCHEMA_VERSION,
    CONFIGURATION_ADOPTION_RECORD_V2_SCHEMA_VERSION,
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.effective_head import (
    ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION,
    AlarmEffectiveConfigurationHead,
)
from ada.alarms.persistence.operational.errors import (
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceError,
    AlarmPersistenceValidationError,
    AlarmPersistenceWriteError,
    AlarmRecoveryRequiredError,
)
from ada.alarms.persistence.operational.models import (
    ENGINE_COMMIT_RECORD_SCHEMA_VERSION,
    ENGINE_COMMIT_RECORD_V2_SCHEMA_VERSION,
    ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION,
    GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
    GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION,
    GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
    JOURNAL_HEAD_SCHEMA_VERSION,
    CommitBatchResult,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
    JournalEntry,
    JournalHead,
    JournalPosition,
    RecoveryResult,
    parse_segment_id,
    segment_id_for_evaluated_at,
)
from ada.alarms.persistence.operational.paths import AlarmPersistencePaths
from ada.alarms.persistence.operational.store import (
    AlarmPersistence,
    AuthorityCheck,
    MutationFence,
)

from ada.alarms.persistence.operational.technical_incidents import (
    build_technical_incident_commit,
    read_open_technical_incidents,
    snapshot_technical_incidents,
)

__version__ = '1.0.0'

__all__ = [
    'CONFIGURATION_ADOPTION_RECORD_SCHEMA_VERSION',
    'CONFIGURATION_ADOPTION_RECORD_V2_SCHEMA_VERSION',
    'AlarmArtifactRefSnapshot',
    'ConfigurationAdoptionRecord',
    'ConfigurationAdoptionRecordV2',
    'GroupCommitReference',
    'ENGINE_COMMIT_RECORD_SCHEMA_VERSION',
    'ENGINE_COMMIT_RECORD_V2_SCHEMA_VERSION',
    'ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION',
    'GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION',
    'GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION',
    'GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION',
    'JOURNAL_HEAD_SCHEMA_VERSION',
    'ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION',
    'AlarmEffectiveConfigurationHead',
    'AlarmPersistence',
    'AlarmPersistenceConflictError',
    'AlarmPersistenceCorruptionError',
    'AlarmPersistenceError',
    'AlarmPersistencePaths',
    'AlarmPersistenceValidationError',
    'AlarmPersistenceWriteError',
    'AlarmRecoveryRequiredError',
    'AuthorityCheck',
    'CommitBatchResult',
    'EngineCommitMetadata',
    'EngineCommitRecord',
    'GroupRuntimeSnapshot',
    'JournalEntry',
    'JournalHead',
    'JournalPosition',
    'MutationFence',
    'RecoveryResult',
    '__version__',
    'parse_segment_id',
    'segment_id_for_evaluated_at',
    'build_technical_incident_commit',
    'read_open_technical_incidents',
    'snapshot_technical_incidents',
]
