# Espejo pedagógico: conserva el comportamiento productivo y documenta la responsabilidad de este módulo.
class KpiRuntimeError(RuntimeError):
    pass


class KpiRuntimeConfigurationError(KpiRuntimeError):
    pass


class KpiRuntimeWatermarkError(KpiRuntimeError):
    pass


class KpiRuntimeSourceStateError(KpiRuntimeError):
    pass


class KpiRuntimeDataError(KpiRuntimeError):
    pass
