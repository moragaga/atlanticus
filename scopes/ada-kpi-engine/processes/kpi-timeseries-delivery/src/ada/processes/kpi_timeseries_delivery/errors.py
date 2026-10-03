class KpiTimeseriesDeliveryError(Exception):
    pass


class KpiTimeseriesDeliveryConfigurationError(KpiTimeseriesDeliveryError):
    pass


class KpiTimeseriesDeliveryReadinessPending(KpiTimeseriesDeliveryError):
    pass


class KpiTimeseriesDeliveryRepositoryError(KpiTimeseriesDeliveryError):
    pass


class KpiTimeseriesDeliveryPublicationError(KpiTimeseriesDeliveryError):
    pass
