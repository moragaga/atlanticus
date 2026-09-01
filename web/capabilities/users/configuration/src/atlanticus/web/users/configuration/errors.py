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
