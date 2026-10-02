class KpiDeliveryProcessError(RuntimeError):
    pass


class KpiDeliveryConfigurationError(KpiDeliveryProcessError, ValueError):
    pass


class KpiDeliveryReadinessPending(KpiDeliveryProcessError):
    pass


class KpiDeliveryRepositoryError(KpiDeliveryProcessError):
    pass


class KpiDeliveryPublicationError(KpiDeliveryProcessError):
    pass
