# Unifica las dos vías administrativas sin confundir autenticación con autorización.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.compositions.deployment_access_manager.session import (
    DeploymentRootSession,
    DeploymentRootSessionError,
)
from atlanticus.web.deployment_access import DeploymentAccessStorageError
from atlanticus.web.manager import ManagerPrincipal


class RootManagerAccessError(ValueError):
    pass


# Esta clase resuelve una identidad administrativa verificable para cada solicitud.
class RootManagerAccess:
    def __init__(
        self,
        *,
        root_session: DeploymentRootSession,
        authenticated_root: Callable[[], ManagerPrincipal | None] | None = None,
    ) -> None:
        if not isinstance(root_session, DeploymentRootSession):
            raise RootManagerAccessError('ROOT access requires DeploymentRootSession')
        if authenticated_root is not None and not callable(authenticated_root):
            raise RootManagerAccessError('Authenticated ROOT provider must be callable')
        self._root_session = root_session
        self._authenticated_root = authenticated_root

    @property
    # Expone la sesión original para impedir composiciones con referencias divergentes.
    def root_session(self) -> DeploymentRootSession:
        return self._root_session

    # Prioriza la sesión de material independiente; ante su ausencia resuelve el ROOT autenticado.
    def current(self) -> ManagerPrincipal | None:
        root_error: DeploymentRootSessionError | DeploymentAccessStorageError | None = None
        try:
            identity = self._root_session.current()
        except (DeploymentRootSessionError, DeploymentAccessStorageError) as error:
            identity = None
            root_error = error
        if identity is not None:
            return ManagerPrincipal(
                subject_id=f'deployment-root:{identity.material_id}',
                display_name='Deployment ROOT',
                profile_label='ROOT',
                administrative_override=True,
            )
        if self._authenticated_root is not None:
            principal = self._authenticated_root()
            if principal is not None:
                if (
                    not isinstance(principal, ManagerPrincipal)
                    or principal.administrative_override is not True
                ):
                    raise RootManagerAccessError(
                        'Authenticated ROOT provider returned an invalid principal'
                    )
                return principal
        if root_error is not None:
            raise root_error
        return None
