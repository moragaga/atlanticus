# Espejo pedagógico: explica el orden durable batch→watermark y la idempotencia sin alterar la semántica.
class KpiPersistenceError(RuntimeError):
    pass


class KpiPersistenceOrderError(KpiPersistenceError):
    pass


class KpiPersistenceCorruptionError(KpiPersistenceError):
    pass
