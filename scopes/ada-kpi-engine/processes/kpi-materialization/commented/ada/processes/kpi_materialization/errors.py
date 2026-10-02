# Espejo pedagógico del proceso KPI Materialization: errors.py.
# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationConnectionsError(ValueError):
    pass


# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationAcquisitionError(RuntimeError):
    pass


# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationIterationError(RuntimeError):
    pass


# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationSettingsError(ValueError):
    pass
