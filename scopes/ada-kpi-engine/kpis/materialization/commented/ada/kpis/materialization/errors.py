# Espejo pedagógico de los errores propios del contrato y almacenamiento local.
# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationContractError(ValueError):
    pass


# Agrupa una responsabilidad con estado o ciclo de vida propio.
class KpiMaterializationStoreError(RuntimeError):
    pass
