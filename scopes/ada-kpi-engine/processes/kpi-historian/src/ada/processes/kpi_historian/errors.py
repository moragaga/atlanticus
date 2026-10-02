class KpiHistorianError(RuntimeError):
    pass


class KpiHistorianConfigurationError(KpiHistorianError):
    pass


class KpiHistorianRepositoryError(KpiHistorianError):
    pass


class KpiHistorianHistoryError(KpiHistorianError):
    pass
