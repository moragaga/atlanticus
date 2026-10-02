# Espejo pedagógico de readiness de KPI Latest Delivery: errors.py.
# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryProcessError(RuntimeError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryConfigurationError(KpiDeliveryProcessError, ValueError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryReadinessPending(KpiDeliveryProcessError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryRepositoryError(KpiDeliveryProcessError):
    pass


# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryPublicationError(KpiDeliveryProcessError):
    pass
