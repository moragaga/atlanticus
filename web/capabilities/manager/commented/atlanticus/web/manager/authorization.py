# Espejo pedagógico: mantiene el mismo AST que producción y documenta el contrato Manager en español.
from typing import Protocol

from atlanticus.web.manager.models import ManagerEntry, ManagerModule, ManagerPrincipal

ManagerAuthorizable = ManagerModule | ManagerEntry


class ManagerAuthorizationPolicy(Protocol):
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool: ...


class DefaultManagerAuthorizationPolicy:
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool:
        required = item.access_key
        if required is None:
            return False
        return required in principal.access_keys
