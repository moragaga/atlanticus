# Espejo pedagógico: explica el orden durable batch→watermark y la idempotencia sin alterar la semántica.
from ada.kpis.persistence.commit import KpiPersistence
from ada.kpis.persistence.errors import (
    KpiPersistenceCorruptionError,
    KpiPersistenceError,
    KpiPersistenceOrderError,
)
from ada.kpis.persistence.models import (
    EVALUATION_BATCH_SCHEMA_VERSION,
    KpiCommitResult,
    KpiCommitState,
    KpiEvaluationBatch,
    KpiEvaluationWriteStatus,
)
from ada.kpis.persistence.paths import KpiPersistencePaths
from ada.kpis.persistence.repositories import KpiEvaluationRepository
from ada.kpis.persistence.state import KpiCommitStateRepository

__version__ = '1.0.0'

__all__ = [
    'EVALUATION_BATCH_SCHEMA_VERSION',
    'KpiCommitResult',
    'KpiCommitState',
    'KpiCommitStateRepository',
    'KpiEvaluationBatch',
    'KpiEvaluationRepository',
    'KpiEvaluationWriteStatus',
    'KpiPersistence',
    'KpiPersistenceCorruptionError',
    'KpiPersistenceError',
    'KpiPersistenceOrderError',
    'KpiPersistencePaths',
    '__version__',
]
