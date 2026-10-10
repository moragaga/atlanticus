# Compone el principal que verá la superficie Manager sin perder el fallback normal.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.compositions.deployment_access_manager.access import RootManagerAccess
from atlanticus.web.compositions.deployment_access_manager.session import DeploymentRootSession
from atlanticus.web.manager import ManagerPrincipal


# Conecta la autorización unificada con el contrato existente de ManagerPrincipal.
def compose_root_manager_principal(
    *,
    root_session: DeploymentRootSession,
    fallback: Callable[[], ManagerPrincipal],
    root_access: RootManagerAccess | None = None,
) -> Callable[[], ManagerPrincipal]:
    if not isinstance(root_session, DeploymentRootSession):
        raise TypeError('ROOT principal composition requires DeploymentRootSession')
    if not callable(fallback):
        raise TypeError('ROOT principal composition requires a fallback principal provider')
    if root_access is not None and (
        not isinstance(root_access, RootManagerAccess)
        or root_access.root_session is not root_session
    ):
        raise TypeError('ROOT principal composition requires a matching ROOT access')
    access = root_access or RootManagerAccess(root_session=root_session)

    def provider() -> ManagerPrincipal:
        principal = access.current()
        return principal if principal is not None else fallback()

    return provider
