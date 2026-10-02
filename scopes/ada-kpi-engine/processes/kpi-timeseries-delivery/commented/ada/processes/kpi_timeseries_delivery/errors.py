# Espejo comentado de la implementación productiva.
class KpiTimeseriesDeliveryError(Exception):
    pass


class KpiTimeseriesDeliveryConfigurationError(KpiTimeseriesDeliveryError):
    pass


class KpiTimeseriesDeliveryRepositoryError(KpiTimeseriesDeliveryError):
    pass
