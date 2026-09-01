# Define errores públicos sanitizados del proceso.

# Mantiene aislada la responsabilidad de KpiDeliveryProcessError.
class KpiDeliveryProcessError(RuntimeError):
    pass


# Mantiene aislada la responsabilidad de KpiDeliveryConfigurationError.
class KpiDeliveryConfigurationError(KpiDeliveryProcessError, ValueError):
    pass


# Mantiene aislada la responsabilidad de KpiDeliveryRepositoryError.
class KpiDeliveryRepositoryError(KpiDeliveryProcessError):
    pass
