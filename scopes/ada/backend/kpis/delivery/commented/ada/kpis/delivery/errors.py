# Error de validación contractual del dominio Delivery.
# Se separa de TypeError para distinguir datos con tipo correcto pero semántica inválida.

class KpiDeliveryValidationError(ValueError):
    pass
