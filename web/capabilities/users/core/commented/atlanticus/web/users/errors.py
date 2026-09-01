# Errores específicos del dominio Users runtime.
# Se mantienen separados de Identity para conservar responsabilidades claras.

class UsersDefinitionError(ValueError):
    pass


class UsersSourceUnavailableError(RuntimeError):
    pass


class UsersIdentityConflictError(RuntimeError):
    pass


class UsersContextError(RuntimeError):
    pass
