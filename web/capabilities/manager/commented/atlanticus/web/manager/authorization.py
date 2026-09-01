# Espejo pedagógico: conserva la misma lógica del archivo productivo.
# Los comentarios documentan la responsabilidad sin cambiar el comportamiento.
# Separa permisos de lectura, validación, publicación y proyección.
from typing import Protocol

from atlanticus.web.manager.models import ManagerModule, ManagerPrincipal


class ManagerAuthorizationPolicy(Protocol):
    def can_view(self, principal: ManagerPrincipal, module: ManagerModule) -> bool: ...

    def can_validate(self, principal: ManagerPrincipal, module: ManagerModule) -> bool: ...

    def can_publish(self, principal: ManagerPrincipal, module: ManagerModule) -> bool: ...

    def can_project(self, principal: ManagerPrincipal, module: ManagerModule) -> bool: ...


class DefaultManagerAuthorizationPolicy:
    def can_view(self, principal: ManagerPrincipal, module: ManagerModule) -> bool:
        return self._has_access(principal, module.access.view)

    def can_validate(self, principal: ManagerPrincipal, module: ManagerModule) -> bool:
        return self._has_access(principal, module.access.validate)

    def can_publish(self, principal: ManagerPrincipal, module: ManagerModule) -> bool:
        return self._has_access(principal, module.access.publish)

    def can_project(self, principal: ManagerPrincipal, module: ManagerModule) -> bool:
        return self._has_access(principal, module.access.project)

    def _has_access(self, principal: ManagerPrincipal, required: str | None) -> bool:
        if principal.is_local or 'administrator' in principal.profile_keys:
            return True
        if required is None:
            return False
        return required in principal.access_keys
