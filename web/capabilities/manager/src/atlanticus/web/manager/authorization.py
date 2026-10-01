from typing import Protocol

from atlanticus.web.manager.models import ManagerEntry, ManagerModule, ManagerPrincipal

ManagerAuthorizable = ManagerModule | ManagerEntry


def manager_access_granted(principal: ManagerPrincipal, access_key: str | None) -> bool:
    if access_key is None:
        return False
    if principal.administrative_override:
        return True
    return access_key in principal.access_keys


class ManagerAuthorizationPolicy(Protocol):
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool: ...


class DefaultManagerAuthorizationPolicy:
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool:
        return manager_access_granted(principal, item.access_key)
