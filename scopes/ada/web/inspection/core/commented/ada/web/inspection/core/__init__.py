# Expone únicamente los contratos públicos necesarios para consumidores y adapters inyectados.
from ada.web.inspection.core.contracts import (
    KpiDefinition,
    KpiDefinitionFields,
    KpiDefinitionProvider,
    KpiDefinitionSnapshot,
    KpiInspectionResult,
)
from ada.web.inspection.core.store import KpiDefinitionSnapshotStore

# Expone contratos y store reusable sin arrastrar infraestructura remota.
__all__ = [
    'KpiDefinition',
    'KpiDefinitionFields',
    'KpiDefinitionProvider',
    'KpiDefinitionSnapshot',
    'KpiDefinitionSnapshotStore',
    'KpiInspectionResult',
]
