# Se definen errores separados para contrato, referencias y persistencia; nunca incluir credenciales en mensajes.
class OperationalIdentificationError(ValueError):
    pass


class OperationalReferenceError(OperationalIdentificationError):
    pass


class OperationalPersistenceError(RuntimeError):
    pass
