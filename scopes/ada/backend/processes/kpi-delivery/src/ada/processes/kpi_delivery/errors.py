class KpiDeliveryProcessError(RuntimeError):
    pass


class KpiDeliveryConfigurationError(KpiDeliveryProcessError, ValueError):
    pass


class KpiDeliveryRepositoryError(KpiDeliveryProcessError):
    pass
