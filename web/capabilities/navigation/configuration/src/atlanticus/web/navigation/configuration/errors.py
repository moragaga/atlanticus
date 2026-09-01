class NavigationConfigurationError(RuntimeError):
    pass


class NavigationConfigurationValidationError(NavigationConfigurationError):
    pass


class NavigationConfigurationSourceError(NavigationConfigurationError):
    pass


class NavigationConfigurationPublisherError(NavigationConfigurationError):
    pass


class NavigationConfigurationProjectionError(NavigationConfigurationError):
    pass
