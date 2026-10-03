# Errores del proceso Timeseries Delivery.
# Espejo pedagógico; los comentarios no alteran el AST productivo.
# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryError(Exception):
    pass


# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryConfigurationError(KpiTimeseriesDeliveryError):
    pass


# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryReadinessPending(KpiTimeseriesDeliveryError):
    pass


# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryRepositoryError(KpiTimeseriesDeliveryError):
    pass


# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryPublicationError(KpiTimeseriesDeliveryError):
    pass
