# Separa errores de validación, Source y Projection.
class KpiConfigurationValidationError(ValueError):
    pass


class KpiConfigurationSourceError(RuntimeError):
    pass


class KpiConfigurationProjectionError(RuntimeError):
    pass
