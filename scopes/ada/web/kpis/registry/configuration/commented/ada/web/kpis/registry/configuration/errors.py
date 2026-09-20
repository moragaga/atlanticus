# Separa errores de Source y Projection del dominio puro.
# Este archivo es el espejo pedagógico del código productivo equivalente.

class KpiRegistrySourceError(RuntimeError):
    pass


class KpiRegistryProjectionError(RuntimeError):
    pass
