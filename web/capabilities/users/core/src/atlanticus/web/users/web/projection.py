from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html, no_update

from atlanticus.web.modules import WebModule
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.web.projection_workflow import UsersProjectionWorkflow

_LOGGER = logging.getLogger(__name__)
_PREFIX = 'atlanticus-users-projection'


def _id(suffix: str) -> str:
    return f'{_PREFIX}__{suffix}'


@dataclass(frozen=True, slots=True)
class UsersProjectionWebContext:
    workflow: UsersProjectionWorkflow
    can_manage: Callable[[], bool]


def build_users_projection_configuration(context: UsersProjectionWebContext) -> object:
    permitted = context.can_manage()
    return html.Div(
        [
            dcc.Store(id=_id('capture-preview'), storage_type='memory'),
            dcc.Store(id=_id('inspection'), storage_type='memory'),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.H3('Users Projection'),
                        html.P(
                            'Captura un snapshot aprobado o compara uno existente con el ambiente actual. '
                            'Esta pantalla no modifica perfiles ni configuraciones de Access.'
                        ),
                    ]
                ),
                className='mb-3',
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4('Capturar snapshot'),
                                    html.P('Incluye todos los usuarios promovidos; excluye candidatos.'),
                                    dbc.Button(
                                        'Previsualizar captura',
                                        id=_id('preview-button'),
                                        color='secondary',
                                        outline=True,
                                        disabled=not permitted,
                                    ),
                                    html.Div(id=_id('capture-preview-panel'), className='my-3'),
                                    dbc.Label('Referencia de aprobación'),
                                    dbc.Input(id=_id('capture-reference'), disabled=not permitted),
                                    dcc.Checklist(
                                        id=_id('capture-confirmation'),
                                        options=[{
                                            'label': ' Confirmo la captura de todos los promovidos',
                                            'value': 'confirmed',
                                        }],
                                        value=[],
                                        className='my-3',
                                    ),
                                    dbc.Button(
                                        'Capturar',
                                        id=_id('capture-button'),
                                        disabled=not permitted,
                                        color='primary',
                                    ),
                                    html.Div(id=_id('capture-result'), className='mt-3'),
                                    dcc.Store(id=_id('capture-finished'), storage_type='memory'),
                                ]
                            )
                        ),
                        md=5,
                        className='mb-3',
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4('Comparar y recuperar'),
                                    html.P('Selecciona un snapshot histórico y revisa todas las diferencias.'),
                                    dbc.Label('Snapshot autorizado'),
                                    dcc.Dropdown(
                                        id=_id('snapshot-select'),
                                        placeholder='Seleccionar snapshot',
                                        options=[],
                                        disabled=not permitted,
                                    ),
                                    dbc.Button(
                                        'Actualizar historial',
                                        id=_id('refresh-history'),
                                        color='secondary',
                                        outline=True,
                                        className='my-2 me-2',
                                        disabled=not permitted,
                                    ),
                                    dbc.Button(
                                        'Comparar',
                                        id=_id('inspect-button'),
                                        color='primary',
                                        outline=True,
                                        className='my-2',
                                        disabled=not permitted,
                                    ),
                                    html.Div(id=_id('history-error')),
                                    html.Div(id=_id('inspection-panel'), className='my-3'),
                                    html.H5('Operación'),
                                    dcc.RadioItems(
                                        id=_id('mode'),
                                        options=[
                                            {'label': ' Restauración estricta (solo faltantes)', 'value': 'restore'},
                                            {'label': ' REPLACE (sustitución completa)', 'value': 'replace'},
                                        ],
                                        value='restore',
                                        labelStyle={'display': 'block', 'marginBottom': '0.5rem'},
                                    ),
                                    dbc.Label('Referencia de aprobación', className='mt-3'),
                                    dbc.Input(id=_id('apply-reference'), disabled=not permitted),
                                    dcc.Checklist(
                                        id=_id('apply-confirmations'),
                                        options=[
                                            {'label': ' Confirmo la ventana de mantenimiento', 'value': 'maintenance'},
                                            {
                                                'label': ' Revisé las sesiones y revocaciones necesarias',
                                                'value': 'revocations',
                                            },
                                        ],
                                        value=[],
                                        className='my-3',
                                        labelStyle={'display': 'block'},
                                    ),
                                    dbc.Label('Escribe RESTORE o REPLACE para confirmar'),
                                    dbc.Input(id=_id('typed-confirmation'), disabled=not permitted),
                                    dbc.Button(
                                        'Ejecutar operación',
                                        id=_id('apply-button'),
                                        color='danger',
                                        className='mt-3',
                                        disabled=not permitted,
                                    ),
                                    html.Div(id=_id('apply-result'), className='mt-3'),
                                ]
                            )
                        ),
                        md=7,
                        className='mb-3',
                    ),
                ]
            ),
        ],
        className='atlanticus-bootstrap container-fluid py-3',
    )


def create_users_projection_web_module(context: UsersProjectionWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_projection_callbacks(app, context)

    return WebModule(
        name='atlanticus-users-projection',
        register_callbacks=register_callbacks,
    )


def register_users_projection_callbacks(app: object, context: UsersProjectionWebContext) -> None:
    @app.callback(
        Output(_id('snapshot-select'), 'options'),
        Output(_id('history-error'), 'children'),
        Input(_id('refresh-history'), 'n_clicks'),
        Input(_id('capture-finished'), 'data'),
    )
    def history(_refresh, _captured):
        if not context.can_manage():
            return [], _error('Not authorized to view Users snapshots')
        try:
            return [
                {'label': snapshot_id, 'value': snapshot_id}
                for snapshot_id in context.workflow.history()
            ], None
        except Exception:
            _LOGGER.exception('Could not list Users snapshots')
            return [], _error('Could not list Users snapshots')

    @app.callback(
        Output(_id('capture-preview'), 'data'),
        Output(_id('capture-preview-panel'), 'children'),
        Input(_id('preview-button'), 'n_clicks'),
        prevent_initial_call=True,
    )
    def preview_capture(clicks):
        if not clicks or not context.can_manage():
            return no_update, _error('Not authorized to preview Users capture')
        try:
            document = context.workflow.preview_capture()
            return document, html.Div(
                [
                    html.P(f"Promovidos: {len(document['approved_ids'])}"),
                    html.P(f"Candidatos excluidos: {len(document['candidate_ids'])}"),
                    html.Small(f"Digest: {document['digest']}"),
                ]
            )
        except (UsersDefinitionError, RuntimeError) as error:
            return None, _error(str(error))
        except Exception:
            _LOGGER.exception('Users capture preview failed')
            return None, _error('Could not preview Users capture')

    @app.callback(
        Output(_id('capture-result'), 'children'),
        Output(_id('capture-preview'), 'data', allow_duplicate=True),
        Output(_id('capture-finished'), 'data'),
        Input(_id('capture-button'), 'n_clicks'),
        State(_id('capture-preview'), 'data'),
        State(_id('capture-reference'), 'value'),
        State(_id('capture-confirmation'), 'value'),
        prevent_initial_call=True,
    )
    def capture(clicks, preview, reference, confirmations):
        if not clicks or not context.can_manage():
            return _error('Not authorized to capture Users snapshots'), no_update, no_update
        if 'confirmed' not in (confirmations or []) or not isinstance(preview, dict):
            return _error('Review the preview and explicitly confirm capture'), no_update, no_update
        try:
            result = context.workflow.capture(preview, reference)
            return _notice(
                f"Snapshot {result['snapshot_id']} capturado con {result['approved_count']} usuarios."
            ), None, result['snapshot_id']
        except (UsersDefinitionError, RuntimeError) as error:
            return _error(str(error)), None, no_update
        except Exception:
            _LOGGER.exception('Users capture failed')
            return _error('Could not capture Users snapshot'), None, no_update

    @app.callback(
        Output(_id('inspection'), 'data'),
        Output(_id('inspection-panel'), 'children'),
        Input(_id('inspect-button'), 'n_clicks'),
        State(_id('snapshot-select'), 'value'),
        prevent_initial_call=True,
    )
    def inspect(clicks, snapshot_id):
        if not clicks or not context.can_manage():
            return None, _error('Not authorized to compare Users snapshots')
        if not isinstance(snapshot_id, str) or not snapshot_id:
            return None, _error('Select a snapshot first')
        try:
            result = context.workflow.inspect(snapshot_id)
            return result, _render_inspection(result)
        except (UsersDefinitionError, RuntimeError) as error:
            return None, _error(str(error))
        except Exception:
            _LOGGER.exception('Users comparison failed')
            return None, _error('Could not compare Users snapshot')

    @app.callback(
        Output(_id('apply-result'), 'children'),
        Output(_id('inspection'), 'data', allow_duplicate=True),
        Input(_id('apply-button'), 'n_clicks'),
        State(_id('inspection'), 'data'),
        State(_id('snapshot-select'), 'value'),
        State(_id('mode'), 'value'),
        State(_id('apply-reference'), 'value'),
        State(_id('apply-confirmations'), 'value'),
        State(_id('typed-confirmation'), 'value'),
        prevent_initial_call=True,
    )
    def apply(clicks, inspection, selected_snapshot, mode, reference, confirmations, typed):
        if not clicks or not context.can_manage():
            return _error('Not authorized to recover Users'), no_update
        if not isinstance(inspection, dict) or inspection.get('snapshot_id') != selected_snapshot:
            return _error('Select and compare the snapshot before applying changes'), None
        selected = set(confirmations or [])
        try:
            result = context.workflow.apply(
                inspection=inspection,
                mode=mode,
                approval_reference=reference,
                maintenance_confirmed='maintenance' in selected,
                revocations_reviewed='revocations' in selected,
                typed_confirmation=typed,
            )
            return _notice(
                f"Operación {result['operation_id']} completada. "
                f"Creados: {result['created']}; modificados: {result['updated']}; "
                f"eliminados: {result['deleted']}. Vuelve a comparar antes de otra operación."
            ), None
        except (UsersDefinitionError, RuntimeError) as error:
            return _error(str(error)), None
        except Exception:
            _LOGGER.exception('Users recovery failed')
            return _error('Users recovery did not complete; inspect persisted audit before retry'), None


def _render_inspection(document: dict[str, object]) -> object:
    rows = [
        html.Tr([
            html.Td(item['user_id']),
            html.Td(item['kind']),
            html.Td(', '.join(item['fields']) or '—'),
        ])
        for item in document['differences']
    ]
    if document['discarded_candidate_ids']:
        rows.extend(
            html.Tr([html.Td(user_id), html.Td('discard candidate'), html.Td('Registry')])
            for user_id in document['discarded_candidate_ids']
        )
    return html.Div(
        [
            dbc.Alert(
                f"Origen: {document['origin_environment']} · Aprobados: {document['approved_count']} · "
                f"Registro: {document['registry_state']}",
                color='secondary',
            ),
            html.P(f"Digest: {document['snapshot_digest']}", className='small text-muted'),
            html.P(
                f"Crear: {len(document['create_ids'])} · "
                f"Modificar: {len(document['update_ids'])} · "
                f"Eliminar: {len(document['delete_ids'])} · "
                f"Descartar candidatos: {len(document['discarded_candidate_ids'])}"
            ),
            dbc.Alert(
                'RESTORE disponible' if document['can_restore'] else 'RESTORE bloqueado',
                color='success' if document['can_restore'] else 'warning',
            ),
            dbc.Alert(
                'REPLACE disponible' if document['can_replace'] else 'REPLACE bloqueado',
                color='success' if document['can_replace'] else 'danger',
            ),
            dbc.Table(
                [
                    html.Thead(html.Tr([html.Th('Usuario'), html.Th('Diferencia'), html.Th('Campos')])),
                    html.Tbody(rows or [html.Tr(html.Td('Sin diferencias', colSpan=3))]),
                ],
                bordered=True,
                responsive=True,
                size='sm',
            ),
        ]
    )


def _notice(message: str) -> object:
    return dbc.Alert(message, color='success')


def _error(message: str) -> object:
    return dbc.Alert(message, color='danger')
