# Espejo pedagógico: Implementa el dominio administrativo genérico de Users: draft validable, Source versionado, proyección y adapters.

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
