# Expone únicamente los contratos públicos necesarios para consumidores y adapters inyectados.
from ada.web.inspection.core.contracts import (
    KpiDefinition,
    KpiDefinitionFields,
    KpiDefinitionProvider,
    KpiDefinitionSnapshot,
    KpiInspectionResult,
)

__all__ = [
    'KpiDefinition',
    'KpiDefinitionFields',
    'KpiDefinitionProvider',
    'KpiDefinitionSnapshot',
    'KpiInspectionResult',
]
