# Espejo pedagógico del módulo operacional errors.py.
# Mantiene la lógica y los contratos del archivo productivo correspondiente.
from __future__ import annotations


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmPersistenceError(RuntimeError):
    pass


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmPersistenceValidationError(AlarmPersistenceError, ValueError):
    pass


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmPersistenceCorruptionError(AlarmPersistenceError):
    pass


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmPersistenceConflictError(AlarmPersistenceError):
    pass


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmPersistenceWriteError(AlarmPersistenceError):
    pass


# Implementa una operación del contrato de persistencia y recuperación.
class AlarmRecoveryRequiredError(AlarmPersistenceError):
    pass
