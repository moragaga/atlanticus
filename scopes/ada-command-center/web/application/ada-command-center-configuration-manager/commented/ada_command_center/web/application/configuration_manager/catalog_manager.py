from __future__ import annotations

from collections.abc import Callable

from dash import Input, Output, State, ctx, dcc, html, no_update

from ada_command_center.tools.discovery_cosmos.manager import (
    AdoptedToolCatalog,
    ToolCatalogManagerConflictError,
    ToolCatalogManagerService,
)
from atlanticus.web.manager import ManagerEntry, ManagerPrincipal
from atlanticus.web.modules import WebModule

TOOL_CATALOG_ACCESS_KEY = 'tools.manage'
_DISCOVER = 'acc-tool-catalog-discover'
_CONFIRM = 'acc-tool-catalog-confirm'
_ADOPTED = 'acc-tool-catalog-adopted'
_STATE = 'acc-tool-catalog-preview-state'
_STATUS = 'acc-tool-catalog-status'
_PREVIEW = 'acc-tool-catalog-preview'
_ADOPTED_RESULT = 'acc-tool-catalog-adopted-result'


def _authorized(principal_provider: Callable[[], ManagerPrincipal]) -> bool:
    return TOOL_CATALOG_ACCESS_KEY in principal_provider().access_keys


# La página del catálogo es una entrada administrativa, no un Source/Projection Manager.
def _layout(_services: object) -> object:
    return html.Div(
        [
            dcc.Store(id=_STATE, storage_type='memory'),
            html.P('Las conexiones se abren solamente al inspeccionar o confirmar.'),
            html.Div(
                [
                    html.Button('Descubrir herramientas', id=_DISCOVER, n_clicks=0),
                    html.Button('Confirmar consolidación', id=_CONFIRM, n_clicks=0, disabled=True),
                    html.Button('Ver claves adoptadas', id=_ADOPTED, n_clicks=0),
                ]
            ),
            html.Div(id=_STATUS, role='status'),
            html.Div(id=_PREVIEW),
            html.Div(id=_ADOPTED_RESULT),
        ],
        className='ada-command-center-tool-catalog',
    )


def _adopted_content(catalog: AdoptedToolCatalog) -> object:
    if catalog.revision is None:
        return html.P('Todavía no existe un catálogo confirmado en Storage.')
    return html.Div(
        [
            html.H3('Claves adoptadas'),
            html.P(f'Revisión: {catalog.revision}'),
            html.Table(
                [
                    html.Thead(
                        html.Tr([html.Th('tool_key'), html.Th('Nombre'), html.Th('Release')])
                    ),
                    html.Tbody(
                        [
                            html.Tr(
                                [
                                    html.Td(tool.tool_key),
                                    html.Td(tool.display_name),
                                    html.Td(tool.source_release_id),
                                ]
                            )
                            for tool in catalog.tools
                        ]
                    ),
                ]
            ),
        ]
    )


def create_tool_catalog_manager_entry(
    *,
    manager: ToolCatalogManagerService,
    principal_provider: Callable[[], ManagerPrincipal],
) -> ManagerEntry:
    # La autorización se verifica también en cada acción de servidor.
    def register_callbacks(app: object, _services: object) -> None:
        @app.callback(
            Output(_STATE, 'data'),
            Output(_STATUS, 'children'),
            Output(_ADOPTED_RESULT, 'children'),
            Input(_DISCOVER, 'n_clicks'),
            Input(_CONFIRM, 'n_clicks'),
            Input(_ADOPTED, 'n_clicks'),
            State(_STATE, 'data'),
            prevent_initial_call=True,
        )
        def execute(_discovery, _confirmation, _adopted, state):
            if not _authorized(principal_provider):
                return None, 'Operación no autorizada.', no_update
            action = ctx.triggered_id
            if action == _DISCOVER:
                try:
                    review = manager.inspect()
                except Exception:
                    return None, 'No fue posible completar el descubrimiento.', no_update
                return (
                    {
                        'fingerprint': review.fingerprint,
                        'revision': review.current_revision,
                        'can_confirm': review.can_confirm,
                        'connections': [
                            {
                                'name': conn.connection_name,
                                'status': conn.status,
                                'issue': conn.issue,
                                'tools': [
                                    {
                                        'key': tool.tool_key,
                                        'name': tool.display_name,
                                        'release': tool.source_release_id,
                                    }
                                    for tool in conn.tools
                                ],
                            }
                            for conn in review.connections
                        ],
                        'issue': review.issue,
                    },
                    'Descubrimiento finalizado. Revisa los resultados antes de confirmar.',
                    no_update,
                )
            # Se repite la lectura de Cosmos; el navegador solo conserva una huella.
            if action == _CONFIRM:
                if not isinstance(state, dict) or state.get('can_confirm') is not True:
                    return None, 'Realiza nuevamente el descubrimiento.', no_update
                try:
                    confirmed = manager.confirm(
                        expected_fingerprint=state['fingerprint'],
                        expected_current_revision=state['revision'],
                    )
                except ToolCatalogManagerConflictError:
                    return (
                        None,
                        'Los datos cambiaron. Realiza nuevamente el descubrimiento.',
                        no_update,
                    )
                except Exception:
                    return (
                        None,
                        'La consolidación falló; comprueba Storage y las conexiones.',
                        no_update,
                    )
                return None, 'Consolidación confirmada.', _adopted_content(confirmed)
            if action == _ADOPTED:
                try:
                    adopted = manager.adopted()
                except Exception:
                    return no_update, 'No fue posible consultar el catálogo confirmado.', no_update
                return (
                    no_update,
                    'Catálogo confirmado leído desde Storage.',
                    _adopted_content(adopted),
                )
            return no_update, no_update, no_update

        @app.callback(
            Output(_PREVIEW, 'children'),
            Output(_CONFIRM, 'disabled'),
            Input(_STATE, 'data'),
        )
        def render(state):
            if not isinstance(state, dict):
                return None, True
            rows = []
            for connection in state.get('connections', []):
                rows.append(
                    html.Tr(
                        [
                            html.Td(connection['name']),
                            html.Td(connection['status']),
                            html.Td(connection.get('issue') or ''),
                            html.Td(str(len(connection['tools']))),
                        ]
                    )
                )
                for tool in connection['tools']:
                    rows.append(
                        html.Tr(
                            [
                                html.Td(''),
                                html.Td(tool['key']),
                                html.Td(tool['name']),
                                html.Td(tool['release']),
                            ]
                        )
                    )
            return (
                html.Div(
                    [
                        html.P(state.get('issue') or 'Revisa los candidatos y confirma.'),
                        html.Table(
                            [
                                html.Thead(
                                    html.Tr(
                                        [
                                            html.Th('Conexión'),
                                            html.Th('Estado o key'),
                                            html.Th('Diagnóstico o nombre'),
                                            html.Th('Total o release'),
                                        ]
                                    )
                                ),
                                html.Tbody(rows),
                            ]
                        ),
                    ]
                ),
                state.get('can_confirm') is not True,
            )

    return ManagerEntry(
        key='tool-catalog',
        group_key='configuration',
        title='Consolidación de herramientas',
        route='/tool-catalog',
        order=5,
        description='Inspecciona las herramientas de Cosmos y confirma su catálogo en Storage.',
        layout=_layout,
        access_key=TOOL_CATALOG_ACCESS_KEY,
        web_module=WebModule(
            name='ada-command-center-tool-catalog',
            register_callbacks=register_callbacks,
        ),
    )
