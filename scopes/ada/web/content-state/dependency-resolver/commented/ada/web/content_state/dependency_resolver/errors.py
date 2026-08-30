# Error base de contrato/configuración para dependencias de Content State.
class ContentStateDependencyError(ValueError):
    pass


# Error específico cuando una dependencia declarada no recibió una condición clasificada.
class MissingSourceFreshnessError(ContentStateDependencyError):
    pass
