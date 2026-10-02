# Espejo pedagógico de readiness de KPI Materialization: errors.py.
# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationAcquisitionError(RuntimeError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationRegistryPending(KpiMaterializationAcquisitionError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationIterationError(RuntimeError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationSettingsError(ValueError):
    pass
