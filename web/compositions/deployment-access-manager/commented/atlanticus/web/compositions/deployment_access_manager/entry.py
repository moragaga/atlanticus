# Composición administrativa de solo lectura; no publica secretos ni muta material ROOT.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from dash import Input, Output, html
from flask import has_request_context

from atlanticus.web.compositions.deployment_access_manager.http import (
    ROOT_LOGIN_PATH,
    ROOT_STATUS_PATH,
)
from atlanticus.web.compositions.deployment_access_manager.session import (
    DeploymentRootSession,
    DeploymentRootSessionError,
)
from atlanticus.web.deployment_access import DeploymentAccessStorageError
from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
    ManagerEntry,
    ManagerPrincipal,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

class DeploymentAccessManagerEntryError(ValueError):
    pass


def create_deployment_access_manager_entry(
    *,
    root_session: DeploymentRootSession,
    principal_provider: Callable[[], ManagerPrincipal],
    group_key: str,
    access_key: str = 'deployment-access.manage',
    module_key: str = 'deployment-access',
    route: str = '/deployment-access',
    order: int = 5,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> ManagerEntry:
    if not isinstance(root_session, DeploymentRootSession):
        raise DeploymentAccessManagerEntryError('Deployment Access requires a ROOT session')
    if not callable(principal_provider):
        raise DeploymentAccessManagerEntryError('Deployment Access requires a principal provider')
    policy = authorization if authorization is not None else DefaultManagerAuthorizationPolicy()
    status_id = f'atlanticus-deployment-access-manager-{module_key}-status'
    refresh_id = f'atlanticus-deployment-access-manager-{module_key}-refresh'

    # El control de acceso ocurre también al refrescar, no solo al construir el layout.
    def status_content() -> object:
        if not has_request_context():
            return html.P('La sesión ROOT requiere una solicitud autenticada.')
        try:
            identity = root_session.current()
            if identity is None:
                return html.Div(
                    [
                        html.P('Se requiere una sesión ROOT vigente para consultar el material.'),
                        html.A('Iniciar sesión ROOT', href=ROOT_LOGIN_PATH),
                    ]
                )
            if not policy.can_view(principal_provider(), entry):
                return html.P('No tienes autorización para consultar Deployment Access.')
        except (DeploymentRootSessionError, DeploymentAccessStorageError):
            return html.P('No fue posible verificar la sesión ROOT.')
        expires = datetime.fromtimestamp(identity.expires_at_epoch, tz=UTC).strftime(
            '%Y-%m-%d %H:%M:%S UTC'
        )
        return html.Div(
            [
                html.P('Material ROOT: PRESENT y verificado.'),
                html.P(f'Usuario de servicio: {identity.service_user}'),
                html.P(f'Vigencia de sesión: {expires}'),
                html.A('Gestionar sesión ROOT y cerrar sesión', href=ROOT_STATUS_PATH),
            ]
        )

    def layout(_services: ServiceRegistry) -> object:
        return html.Div(
            [
                html.P(
                    'Consulta de la sesión administrativa ROOT. El material permanece protegido '
                    'en su almacenamiento y no se muestra ni se descarga desde esta página.'
                ),
                html.Div(status_content(), id=status_id, role='status'),
                html.Button('Actualizar estado', id=refresh_id, n_clicks=0),
                html.P(
                    'La creación, rotación y eliminación del material se realizan mediante '
                    'el procedimiento administrativo externo. Esta página no modifica material.'
                ),
            ],
            className='atlanticus-deployment-access-manager',
        )

    # El callback se registra en el WebModule del mismo ManagerEntry.
    def register_callbacks(app: object, _services: ServiceRegistry) -> None:
        @app.callback(Output(status_id, 'children'), Input(refresh_id, 'n_clicks'))
        def refresh_status(_clicks: int | None) -> object:
            return status_content()

    entry = ManagerEntry(
        key=module_key,
        group_key=group_key,
        title='Deployment Access',
        route=route,
        order=order,
        description='Material y sesión ROOT del Manager.',
        layout=layout,
        access_key=access_key,
        web_module=WebModule(
            name='deployment-access-manager-entry', register_callbacks=register_callbacks
        ),
    )
    return entry
