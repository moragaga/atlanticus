class KpiPersistenceError(RuntimeError):
    pass


class KpiPersistenceOrderError(KpiPersistenceError):
    pass


class KpiPersistenceCorruptionError(KpiPersistenceError):
    pass
