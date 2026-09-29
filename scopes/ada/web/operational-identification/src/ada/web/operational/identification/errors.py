class OperationalIdentificationError(ValueError):
    pass


class OperationalReferenceError(OperationalIdentificationError):
    pass


class OperationalPersistenceError(RuntimeError):
    pass
