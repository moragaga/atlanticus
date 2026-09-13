# Errores públicos de Users Configuration; el conflicto CAS de Projection tiene tipo propio.
class UsersConfigurationError(Exception):
    pass


class UsersConfigurationValidationError(UsersConfigurationError):
    pass


class UsersConfigurationSourceError(UsersConfigurationError):
    pass


class UsersConfigurationPublisherError(UsersConfigurationError):
    pass


class UsersConfigurationProjectionError(UsersConfigurationError):
    pass


# Permite distinguir un conflicto concurrente real de corrupción o fallo de persistencia.
class UsersConfigurationProjectionConflictError(UsersConfigurationProjectionError):
    pass
