# Errores específicos del contrato descriptivo de KPI.
class KpiDefinitionValidationError(ValueError):
    pass


# Separa errores del documento proyectado de los errores del source.
class KpiDefinitionProjectionError(ValueError):
    pass
