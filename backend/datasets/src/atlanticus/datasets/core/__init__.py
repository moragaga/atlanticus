"""Contratos neutrales para identificar y publicar datasets Atlanticus."""

from atlanticus.datasets.core.errors import (
    DatasetDefinitionError,
    DatasetError,
    DatasetTargetError,
    DatasetValidationError,
)
from atlanticus.datasets.core.layouts import DatasetLayout, FileSetLayout, SingleArtifactLayout
from atlanticus.datasets.core.models import (
    DatasetDefinition,
    DatasetKey,
    DatasetPartition,
    DatasetPartKey,
    DatasetTarget,
    MaterializationDefinition,
)
from atlanticus.datasets.core.results import (
    DatasetBatchResult,
    DatasetBatchStatus,
    DatasetPublicationFailure,
    DatasetPublicationResult,
    PublicationQuality,
    PublicationSkipReason,
    PublicationStatus,
)

__version__ = '1.0.0'

__all__ = [
    'DatasetBatchResult',
    'DatasetBatchStatus',
    'DatasetDefinition',
    'DatasetDefinitionError',
    'DatasetError',
    'DatasetKey',
    'DatasetLayout',
    'DatasetPartKey',
    'DatasetPartition',
    'DatasetPublicationFailure',
    'DatasetPublicationResult',
    'DatasetTarget',
    'DatasetTargetError',
    'DatasetValidationError',
    'FileSetLayout',
    'MaterializationDefinition',
    'PublicationQuality',
    'PublicationSkipReason',
    'PublicationStatus',
    'SingleArtifactLayout',
    '__version__',
]
