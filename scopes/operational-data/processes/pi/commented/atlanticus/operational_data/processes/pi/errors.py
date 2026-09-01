# Error base de la composición PI Web API específica de Operational Data.
class PiWebApiProcessError(RuntimeError):
    pass


# Error de configuración resuelta para el proceso PI Web API.
class PiWebApiProcessConfigurationError(PiWebApiProcessError, ValueError):
    pass


# Error del catálogo concreto que Operational Data entrega al producer PI.
class PiWebApiCatalogError(ValueError):
    pass
