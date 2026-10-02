# Espejo pedagógico de KPI Materialization migrado al contrato compartido: errors.py.
# Agrupa una responsabilidad con estado o contrato propio.
class KpiMaterializationAcquisitionError(RuntimeError):
    pass


# Agrupa una responsabilidad con estado o contrato propio.
class KpiMaterializationIterationError(RuntimeError):
    pass


# Agrupa una responsabilidad con estado o contrato propio.
class KpiMaterializationSettingsError(ValueError):
    pass
