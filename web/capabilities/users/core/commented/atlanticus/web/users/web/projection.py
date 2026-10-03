from __future__ import annotations

# Checklist se bloquea por opción porque dbc.Checklist 2.0.4 no acepta disabled a nivel componente.

import logging
from collections.abc import Callable
from dataclasses import dataclass

import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html, no_update

from atlanticus.web.modules import WebModule
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.recovery import UsersRecoveryConflictError
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
            dcc.Store(id=_id('capture-preview')),
            dcc.Store(id=_id('inspection')),
            html.Section(
                [
                    html.H3('Crear snapshot de users-runtime'),
                    html.P(
                        'Materializa Identity + Tool Membership + Profiles + Operational y guarda '
                        'un snapshot inmutable de RuntimeUser para esta Tool.'
                    ),
                    dbc.Button(
                        'Revisar snapshot',
                        id=_id('preview'),
                        n_clicks=0,
                        disabled=not permitted,
                    ),
                    html.Div(id=_id('preview-result')),
                    dbc.Input(
                        id=_id('capture-reference'),
                        placeholder='Referencia de aprobación',
                        disabled=not permitted,
                    ),
                    dbc.Button(
                        'Guardar snapshot',
                        id=_id('capture'),
                        n_clicks=0,
                        disabled=not permitted,
                    ),
                    html.Div(id=_id('capture-result')),
                ]
            ),
            html.Hr(),
            html.Section(
                [
                    html.H3('Reemplazar users-runtime'),
                    html.P(
                        'Selecciona un snapshot aprobado, compara el runtime actual y reemplaza '
                        'el conjunto completo. No modifica Global Users ni Tool Membership.'
                    ),
                    dbc.Button(
                        'Actualizar snapshots',
                        id=_id('refresh-history'),
                        n_clicks=0,
                        disabled=not permitted,
                    ),
                    dcc.Dropdown(
                        id=_id('snapshot'),
                        options=[],
                        clearable=False,
                        disabled=not permitted,
                    ),
                    dbc.Button(
                        'Comparar',
                        id=_id('inspect'),
                        n_clicks=0,
                        disabled=not permitted,
                    ),
                    html.Div(id=_id('inspection-result')),
                    dbc.Input(
                        id=_id('apply-reference'),
                        placeholder='Referencia de aprobación',
                        disabled=not permitted,
                    ),
                    dbc.Checklist(
                        id=_id('confirmations'),
                        options=[
                            {
                                'label': 'Ambiente en mantenimiento',
                                'value': 'maintenance',
                                'disabled': not permitted,
                            },
                            {
                                'label': 'Sesiones y revocaciones revisadas',
                                'value': 'revocations',
                                'disabled': not permitted,
                            },
                        ],
                        value=[],
                    ),
                    dbc.Button(
                        'Reemplazar users-runtime',
                        id=_id('apply'),
                        n_clicks=0,
                        disabled=not permitted,
                    ),
                    html.Div(id=_id('apply-result')),
                ]
            ),
        ],
        className=f'{_PREFIX} atlanticus-bootstrap',
    )


def create_users_projection_web_module(context: UsersProjectionWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_projection_callbacks(app, context)

    return WebModule(name='atlanticus-users-projection', register_callbacks=register_callbacks)


def register_users_projection_callbacks(app: object, context: UsersProjectionWebContext) -> None:
    @app.callback(
        Output(_id('preview-result'), 'children'),
        Output(_id('capture-preview'), 'data'),
        Input(_id('preview'), 'n_clicks'),
        prevent_initial_call=True,
    )
    def preview(clicks):
        if not clicks or not context.can_manage():
            return no_update, no_update
        try:
            result = context.workflow.preview_capture()
            return (
                _notice(
                    f"RuntimeUsers a capturar: {len(result['approved_ids'])}. "
                    f"Digest: {result['digest']}."
                ),
                result,
            )
        except Exception as error:
            _LOGGER.exception('Users snapshot preview failed')
            return _error('No se pudo materializar el snapshot.', error), None

    @app.callback(
        Output(_id('capture-result'), 'children'),
        Output(_id('capture-preview'), 'data', allow_duplicate=True),
        Input(_id('capture'), 'n_clicks'),
        State(_id('capture-preview'), 'data'),
        State(_id('capture-reference'), 'value'),
        prevent_initial_call=True,
    )
    def capture(clicks, preview, reference):
        if not clicks or not context.can_manage():
            return no_update, no_update
        if not isinstance(preview, dict):
            return _error('Revisa el snapshot antes de guardarlo.'), no_update
        try:
            saved = context.workflow.capture(preview, reference or '')
            return (
                _notice(
                    f"Snapshot {saved['snapshot_id']} guardado con "
                    f"{saved['approved_count']} RuntimeUsers."
                ),
                None,
            )
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return _error('No se guardó el snapshot.', error), no_update

    @app.callback(
        Output(_id('snapshot'), 'options'),
        Input(_id('refresh-history'), 'n_clicks'),
        Input(_id('capture-result'), 'children'),
    )
    def history(_refresh, _capture_result):
        if not context.can_manage():
            return []
        try:
            return [
                {
                    'label': (
                        f"{item.get('saved_at_utc') or 'Fecha no disponible'} · "
                        f"{item['snapshot_id']}"
                    ),
                    'value': item['snapshot_id'],
                }
                for item in context.workflow.history_details()
            ]
        except Exception:
            _LOGGER.exception('Could not list Users snapshots')
            return []

    @app.callback(
        Output(_id('inspection-result'), 'children'),
        Output(_id('inspection'), 'data'),
        Input(_id('inspect'), 'n_clicks'),
        State(_id('snapshot'), 'value'),
        prevent_initial_call=True,
    )
    def inspect(clicks, snapshot_id):
        if not clicks or not context.can_manage() or not isinstance(snapshot_id, str):
            return no_update, no_update
        try:
            result = context.workflow.inspect(snapshot_id)
            return (
                _notice(
                    'Comparación completada. '
                    f"Crear: {len(result['create_ids'])}; "
                    f"Modificar: {len(result['update_ids'])}; "
                    f"Eliminar: {len(result['delete_ids'])}."
                ),
                result,
            )
        except Exception as error:
            _LOGGER.exception('Users snapshot inspection failed')
            return _error('No se pudo comparar el snapshot.', error), None

    @app.callback(
        Output(_id('apply-result'), 'children'),
        Output(_id('inspection'), 'data', allow_duplicate=True),
        Input(_id('apply'), 'n_clicks'),
        State(_id('inspection'), 'data'),
        State(_id('apply-reference'), 'value'),
        State(_id('confirmations'), 'value'),
        prevent_initial_call=True,
    )
    def apply(clicks, inspection, reference, confirmations):
        if not clicks or not context.can_manage():
            return no_update, no_update
        if not isinstance(inspection, dict):
            return _error('Compara un snapshot antes de reemplazar el runtime.'), no_update
        selected = set(confirmations or [])
        if not {'maintenance', 'revocations'} <= selected:
            return _error('Confirma mantenimiento y revisión de sesiones.'), no_update
        try:
            result = context.workflow.apply(
                inspection=inspection,
                approval_reference=reference or '',
                maintenance_confirmed=True,
                revocations_reviewed=True,
                confirmed=True,
            )
            return (
                _notice(
                    f"users-runtime reemplazado. Crear: {result['created']}; "
                    f"modificar: {result['updated']}; eliminar: {result['deleted']}."
                ),
                None,
            )
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return _error('No se reemplazó users-runtime.', error), no_update


def _notice(message: str) -> object:
    return html.Div(message, className=f'{_PREFIX}__notice')


def _error(message: str, error: Exception | None = None) -> object:
    children = [html.Span(message)]
    if error is not None:
        children.append(html.Code(str(error)))
    return html.Div(children, className=f'{_PREFIX}__error')
