class KpiTimeseriesDeliveryError(Exception):
    pass


class KpiTimeseriesDeliveryConfigurationError(KpiTimeseriesDeliveryError):
    pass


class KpiTimeseriesDeliveryRepositoryError(KpiTimeseriesDeliveryError):
    pass
