class UsersDefinitionError(ValueError):
    pass


class UsersRuntimeStoreUnavailableError(RuntimeError):
    pass


class UsersIdentityConflictError(RuntimeError):
    pass


class UsersContextError(RuntimeError):
    pass
