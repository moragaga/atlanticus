# Espejo pedagógico: mantiene el mismo AST que producción y documenta el contrato Manager en español.
from typing import Protocol

from atlanticus.web.manager.models import ManagerEntry, ManagerModule, ManagerPrincipal

ManagerAuthorizable = ManagerModule | ManagerEntry


# Esta regla es la única semántica genérica para autorizar una Manager access key.
def manager_access_granted(principal: ManagerPrincipal, access_key: str | None) -> bool:
    # Un item sin Manager access key no se vuelve visible por override.
    if access_key is None:
        return False
    # El override expresa administración total sin mantener listas exhaustivas de permisos.
    if principal.administrative_override:
        return True
    # Los permisos granulares permanecen disponibles para delegación futura.
    return access_key in principal.access_keys


class ManagerAuthorizationPolicy(Protocol):
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool: ...


class DefaultManagerAuthorizationPolicy:
    def can_view(self, principal: ManagerPrincipal, item: ManagerAuthorizable) -> bool:
        # La policy de visibilidad delega en la misma regla que deben usar las acciones Manager.
        return manager_access_granted(principal, item.access_key)
