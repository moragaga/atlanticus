class UsersConfigurationError(Exception):
    pass


class UsersConfigurationValidationError(UsersConfigurationError):
    pass


class UsersConfigurationSourceError(UsersConfigurationError):
    pass


class UsersConfigurationProjectionError(UsersConfigurationError):
    pass


class UsersConfigurationProjectionConflictError(UsersConfigurationProjectionError):
    pass
