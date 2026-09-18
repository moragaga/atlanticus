# Espejo pedagógico: conserva exactamente el contrato productivo y explica su intención.
class UsersDefinitionError(ValueError):
    pass


class UsersStoreUnavailableError(RuntimeError):
    pass


class UsersRegistryUnavailableError(RuntimeError):
    pass


class UsersRegistryConflictError(RuntimeError):
    pass


class UsersIdentityConflictError(RuntimeError):
    pass


class UserAlreadyPromotedError(RuntimeError):
    pass


class UserPromotionError(RuntimeError):
    pass


class UsersContextError(RuntimeError):
    pass
