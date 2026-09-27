from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.provider import IdentityProvider


def create_identity_provider() -> IdentityProvider:
    raise IdentityConfigurationError('Production IdentityProvider must be supplied by the ADA host')
