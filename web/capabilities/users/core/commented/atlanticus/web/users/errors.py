# Errores específicos del dominio Users runtime.
# Se mantienen separados de Identity para conservar responsabilidades claras.

class UsersDefinitionError(ValueError):
    pass


# Indica que la superficie durable/runtime de Users no pudo resolverse de forma confiable.
class UsersRuntimeStoreUnavailableError(RuntimeError):
    pass


class UsersIdentityConflictError(RuntimeError):
    pass


class UsersContextError(RuntimeError):
    pass
