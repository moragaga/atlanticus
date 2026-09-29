# API pública estable para componer la capacidad de identificación operacional desde ADA Web.
from ada.web.operational.identification.cosmos import CosmosOperationalProjectionStore
from ada.web.operational.identification.errors import (
    OperationalIdentificationError,
    OperationalPersistenceError,
    OperationalReferenceError,
)
from ada.web.operational.identification.keys import CATALOG_SOURCE_KEY, assignment_source_key
from ada.web.operational.identification.models import (
    OperationalAssignment,
    OperationalCatalog,
    Position,
)
from ada.web.operational.identification.service import OperationalIdentificationService
from ada.web.operational.identification.source import OperationalSourceService

__all__ = [
    'CATALOG_SOURCE_KEY',
    'CosmosOperationalProjectionStore',
    'OperationalAssignment',
    'OperationalCatalog',
    'OperationalIdentificationError',
    'OperationalIdentificationService',
    'OperationalPersistenceError',
    'OperationalReferenceError',
    'OperationalSourceService',
    'Position',
    'assignment_source_key',
]
