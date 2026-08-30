# Error de dominio específico para distinguir una configuración inválida de otros ValueError.
class ToolSourceConsumptionValidationError(ValueError):
    pass
