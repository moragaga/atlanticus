# Ofrece inventario Cosmos con un guard administrativo común y consultas explícitas.
from __future__ import annotations

from collections.abc import Callable

from dash import Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate
from flask import has_request_context

from atlanticus.connectivity.cosmos.errors import CosmosError
from atlanticus.web.compositions.deployment_access_manager import (
    DeploymentRootSession,
    DeploymentRootSessionError,
    RootManagerAccess,
)
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationConfigurationError,
    CosmosAdministrationService,
    CosmosInventoryReport,
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


class CosmosInventoryManagerEntryError(ValueError):
    pass


# Conserva el inventario de solo lectura y revalida la autorización en callbacks.
def create_cosmos_inventory_manager_entry(
    *,
    administration: CosmosAdministrationService,
    root_session: DeploymentRootSession,
    principal_provider: Callable[[], ManagerPrincipal],
    group_key: str,
    module_key: str = 'cosmos-administration',
    route: str = '/cosmos-administration',
    order: int = 10,
    access_key: str = 'cosmos-administration.manage',
    max_items: int = 200,
    authorization: ManagerAuthorizationPolicy | None = None,
    root_access: RootManagerAccess | None = None,
) -> ManagerEntry:
    if not isinstance(administration, CosmosAdministrationService):
        raise CosmosInventoryManagerEntryError('Cosmos inventory requires administration service')
    if not isinstance(root_session, DeploymentRootSession):
        raise CosmosInventoryManagerEntryError('Cosmos inventory requires ROOT session')
    if not callable(principal_provider):
        raise CosmosInventoryManagerEntryError('Cosmos inventory requires principal provider')
    if not isinstance(max_items, int) or isinstance(max_items, bool) or not 1 <= max_items <= 200:
        raise CosmosInventoryManagerEntryError('Cosmos inventory limit must be between 1 and 200')
    if root_access is not None and (
        not isinstance(root_access, RootManagerAccess)
        or root_access.root_session is not root_session
    ):
        raise CosmosInventoryManagerEntryError('Cosmos inventory requires matching ROOT access')
    effective_access = root_access or RootManagerAccess(root_session=root_session)
    policy = authorization if authorization is not None else DefaultManagerAuthorizationPolicy()
    connection_id = f'atlanticus-cosmos-admin-{module_key}-connection'
    inspect_id = f'atlanticus-cosmos-admin-{module_key}-inspect'
    report_id = f'atlanticus-cosmos-admin-{module_key}-report'

    # No basta tener el dropdown o la ruta; cada consulta exige ROOT y Manager.
    def is_authorized() -> bool:
        if not has_request_context():
            return False
        try:
            if effective_access.current() is None:
                return False
            return policy.can_view(principal_provider(), entry) is True
        except (DeploymentRootSessionError, DeploymentAccessStorageError):
            return False

    def layout(_services: ServiceRegistry) -> object:
        if not is_authorized():
            return html.P(
                'Se requiere una sesión ROOT o identidad ROOT y autorización Manager vigentes.'
            )
        try:
            connections = administration.list_connections()
        except (CosmosAdministrationConfigurationError, CosmosError):
            return html.P('No fue posible consultar las conexiones Cosmos configuradas.')
        options = [
            {'label': f'{item.connection_ref} — {item.database_name}', 'value': item.connection_ref}
            for item in connections
        ]
        return html.Div(
            [
                html.P('Inventario de solo lectura. No crea, modifica ni elimina recursos Cosmos.'),
                html.Label('Conexión Cosmos', htmlFor=connection_id),
                dcc.Dropdown(
                    id=connection_id,
                    options=options,
                    value=None,
                    clearable=True,
                    placeholder='Selecciona una conexión nombrada',
                ),
                html.Button('Consultar contenedores', id=inspect_id, n_clicks=0),
                html.Div(id=report_id, role='status'),
                html.P(f'Límite por consulta: {max_items} contenedores.'),
            ],
            className='atlanticus-cosmos-administration-manager',
        )

    def register_callbacks(app: object, _services: ServiceRegistry) -> None:
        @app.callback(
            Output(report_id, 'children'),
            Input(inspect_id, 'n_clicks'),
            State(connection_id, 'value'),
            prevent_initial_call=True,
        )
        def inspect_containers(clicks: int | None, connection_ref: str | None) -> object:
            if not isinstance(clicks, int) or clicks <= 0:
                raise PreventUpdate
            if not is_authorized():
                return html.P(
                    'Se requiere una sesión ROOT o identidad ROOT y autorización Manager vigentes.'
                )
            try:
                permitted = {item.connection_ref for item in administration.list_connections()}
                if not isinstance(connection_ref, str) or connection_ref not in permitted:
                    return html.P('Selecciona una conexión Cosmos configurada.')
                report = administration.inventory(
                    connection_ref=connection_ref, max_items=max_items
                )
            except (CosmosAdministrationConfigurationError, CosmosError, ValueError):
                return html.P('No fue posible consultar el inventario Cosmos.')
            return _render_inventory(report)

    entry = ManagerEntry(
        key=module_key,
        group_key=group_key,
        title='Cosmos Administration',
        route=route,
        order=order,
        description='Conexiones nombradas e inventario físico de contenedores Cosmos.',
        layout=layout,
        access_key=access_key,
        web_module=WebModule(
            name=f'cosmos-administration-manager-{module_key}',
            register_callbacks=register_callbacks,
        ),
    )
    return entry


def _render_inventory(report: CosmosInventoryReport) -> object:
    rows = [
        html.Tr(
            [
                html.Td(item.name),
                html.Td(', '.join(item.partition_key_paths)),
                html.Td(
                    'Sin TTL' if item.default_ttl_seconds is None else str(item.default_ttl_seconds)
                ),
            ]
        )
        for item in report.containers
    ]
    if not rows:
        return html.Div(
            [
                html.P(f'Base: {report.database_name}'),
                html.P('No hay contenedores en la base seleccionada.'),
            ]
        )
    return html.Div(
        [
            html.P(f'Conexión: {report.connection_ref} · Base: {report.database_name}'),
            html.P(f'Contenedores encontrados: {len(rows)}'),
            html.Table(
                [
                    html.Thead(
                        html.Tr([html.Th('Contenedor'), html.Th('Partición'), html.Th('TTL (s)')])
                    ),
                    html.Tbody(rows),
                ]
            ),
        ]
    )
