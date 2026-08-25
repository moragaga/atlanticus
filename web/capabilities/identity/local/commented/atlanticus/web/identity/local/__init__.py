# El provider local es determinista y no recibe datos de usuario por variables.
from atlanticus.web.identity.local.provider import LocalIdentityProvider


def create_local_identity_provider() -> LocalIdentityProvider:
    return LocalIdentityProvider()


__all__ = ['LocalIdentityProvider', 'create_local_identity_provider']
