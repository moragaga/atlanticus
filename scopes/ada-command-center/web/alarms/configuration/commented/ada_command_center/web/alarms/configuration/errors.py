# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
class AlarmConfigurationSourceError(RuntimeError):
    pass


class AlarmConfigurationToolDependencyError(ValueError):
    pass


# Los adaptadores local y Cosmos devuelven el mismo error específico sin modificar el Manager.
class AlarmConfigurationProjectionError(RuntimeError):
    pass
