class UsersDefinitionError(ValueError):
    pass


class UsersSourceUnavailableError(RuntimeError):
    pass


class UsersIdentityConflictError(RuntimeError):
    pass


class UsersContextError(RuntimeError):
    pass
