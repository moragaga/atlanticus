# Distingue errores funcionales del Manager y el conflicto optimista de revisión de la fuente.
class ManagerError(Exception):
    pass


class ManagerDefinitionError(ManagerError):
    pass


class ManagerAuthorizationError(ManagerError):
    pass


class ManagerProjectionError(ManagerError):
    pass


class ManagerSourceConflictError(ManagerProjectionError):
    pass
