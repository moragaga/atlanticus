# Errores explícitos del proceso Historian, separados por configuración, repositorio y materialización.
class KpiHistorianError(RuntimeError):
    pass


class KpiHistorianConfigurationError(KpiHistorianError):
    pass


class KpiHistorianRepositoryError(KpiHistorianError):
    pass


class KpiHistorianHistoryError(KpiHistorianError):
    pass
