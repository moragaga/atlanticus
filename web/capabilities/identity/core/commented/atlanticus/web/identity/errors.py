# Define errores propios de Identity y del bootstrap de acceso.
# AccessResolverUnavailableError permite distinguir una falla de Users u otra fuente
# de un problema de credenciales del usuario.

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
