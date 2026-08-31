# Errores de dominio separados para conservar la semántica de cada contrato dentro del mismo wheel.
class ToolSourceConsumptionValidationError(ValueError):
    pass


class ToolSourceOperationalParticipationValidationError(ValueError):
    pass
