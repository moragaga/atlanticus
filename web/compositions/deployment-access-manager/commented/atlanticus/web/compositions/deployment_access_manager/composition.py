from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.compositions.deployment_access_manager.session import DeploymentRootSession
from atlanticus.web.manager import ManagerPrincipal


# El Manager conserva un único principal_provider; ROOT lo sustituye solo si su sesión vale.
def compose_root_manager_principal(
    *,
    root_session: DeploymentRootSession,
    fallback: Callable[[], ManagerPrincipal],
) -> Callable[[], ManagerPrincipal]:
    if not isinstance(root_session, DeploymentRootSession):
        raise TypeError('ROOT principal composition requires DeploymentRootSession')
    if not callable(fallback):
        raise TypeError('ROOT principal composition requires a fallback principal provider')

    # Sin sesión ROOT, siempre se delega al proveedor de identidad existente.
    def provider() -> ManagerPrincipal:
        identity = root_session.current()
        if identity is None:
            return fallback()
        return ManagerPrincipal(
            subject_id=f'deployment-root:{identity.material_id}',
            display_name='Deployment ROOT',
            profile_label='ROOT',
            administrative_override=True,
        )

    return provider
