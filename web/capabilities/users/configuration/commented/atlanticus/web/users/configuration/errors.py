# Base común de errores propios de Users Configuration.
class UsersConfigurationError(Exception):
    pass


class UsersConfigurationValidationError(UsersConfigurationError):
    pass


# SourceError pertenece a la frontera vigente con Source genérico.
class UsersConfigurationSourceError(UsersConfigurationError):
    pass


# ProjectionError traduce fallos del payload Users durante la proyección genérica.
class UsersConfigurationProjectionError(UsersConfigurationError):
    pass


# ConflictError conserva la semántica CAS del ProjectionStore Cosmos vigente.
class UsersConfigurationProjectionConflictError(UsersConfigurationProjectionError):
    pass
