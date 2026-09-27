
# Espejo pedagógico: mismo código ejecutable con comentarios en español.
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.provider import IdentityProvider


# Frontera de implementación del consumidor: esta plantilla debe reemplazarse por Entra real.
def create_identity_provider() -> IdentityProvider:
    raise IdentityConfigurationError('Production IdentityProvider must be supplied by the ADA host')
