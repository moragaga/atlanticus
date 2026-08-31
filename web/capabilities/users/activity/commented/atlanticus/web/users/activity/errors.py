# Define errores propios para separar fallos de contrato y conflictos recuperables.
class UserActivityError(RuntimeError):
    pass


class UserActivityConflictError(UserActivityError):
    pass
