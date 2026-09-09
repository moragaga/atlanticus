# Errores propios de Source y Projection sin alterar los errores del modelo Tool.
class ToolLifecycleSourceError(RuntimeError):
    pass


class ToolLifecycleProjectionError(RuntimeError):
    pass
