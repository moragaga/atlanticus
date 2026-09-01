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
