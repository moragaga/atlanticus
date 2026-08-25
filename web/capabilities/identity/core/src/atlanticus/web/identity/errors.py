class IdentityDefinitionError(ValueError):
    pass


class IdentityConfigurationError(RuntimeError):
    pass


class IdentityAuthenticationError(RuntimeError):
    pass


class IdentityProviderUnavailableError(RuntimeError):
    pass


class AccessResolverUnavailableError(RuntimeError):
    pass


class AccessContextError(RuntimeError):
    pass
