# Error de contrato o validación de una definición KPI.
class KpiDefinitionValidationError(ValueError):
    pass


# Error de disponibilidad o concurrencia de la fuente autoritativa.
class KpiDefinitionSourceError(RuntimeError):
    pass


# Error durante la construcción o actualización de la proyección.
class KpiDefinitionProjectionError(ValueError):
    pass
