from typing import Protocol

from atlanticus.web.manager.models import ManagerModule, ManagerPrincipal


class ManagerAuthorizationPolicy(Protocol):
    def can_view(self, principal: ManagerPrincipal, module: ManagerModule) -> bool: ...


class DefaultManagerAuthorizationPolicy:
    def can_view(self, principal: ManagerPrincipal, module: ManagerModule) -> bool:
        required = module.access_key
        if required is None:
            return False
        return required in principal.access_keys
