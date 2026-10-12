from __future__ import annotations

# Esta pantalla solo reconstruye la sección base de Users, sin tomar ownership de Access ni Operational.

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html, no_update

from atlanticus.web.modules import WebModule
from atlanticus.web.users.reconstruction import (
    UsersReconstructionConflictError,
    UsersReconstructionPreview,
    UsersReconstructionWorkflow,
)

_LOGGER = logging.getLogger(__name__)
_PREFIX = 'atlanticus-users-reconstruction'


def _id(suffix: str) -> str:
    return f'{_PREFIX}__{suffix}'


@dataclass(frozen=True, slots=True)
class UsersReconstructionWebContext:
    workflow: UsersReconstructionWorkflow
    can_manage: Callable[[], bool]
    title: str = 'Reconstrucción de usuarios'
    description: str = 'Reconstruye Identity, Membership y Profile desde sus fuentes vigentes.'
    action_label: str = 'Reconstruir'
    complete_label: str = 'Reconstrucción completada'


def inspection_document(preview: UsersReconstructionPreview) -> dict[str, object]:
    # El digest incluye contenido y diferencias: permite detectar inspecciones obsoletas antes de aplicar.
    document = {
        'users': [user.to_document() for user in preview.desired_users],
        'create_ids': list(preview.create_ids),
        'update_ids': list(preview.update_ids),
        'disable_ids': list(preview.disable_ids),
    }
    fingerprint = hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    return {
        'create_ids': document['create_ids'],
        'update_ids': document['update_ids'],
        'disable_ids': document['disable_ids'],
        'fingerprint': fingerprint,
    }


def build_users_reconstruction_configuration(context: UsersReconstructionWebContext) -> object:
    permitted = context.can_manage()
    return html.Div(
        [
            html.H3(context.title),
            html.P(context.description),
            dcc.Store(id=_id('inspection'), storage_type='memory'),
            dbc.Button('Inspeccionar', id=_id('inspect'), n_clicks=0, disabled=not permitted),
            html.Div(id=_id('inspection-result')),
            dbc.Checklist(
                id=_id('confirmation'),
                options=[{'label': 'Confirmo la publicación', 'value': 'confirmed', 'disabled': not permitted}],
                value=[],
            ),
            dbc.Button(context.action_label, id=_id('apply'), n_clicks=0, disabled=not permitted),
            html.Div(id=_id('apply-result')),
        ],
        className=f'{_PREFIX} atlanticus-bootstrap',
    )


def create_users_reconstruction_web_module(context: UsersReconstructionWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_reconstruction_callbacks(app, context)

    return WebModule(name='atlanticus-users-reconstruction', register_callbacks=register_callbacks)


def register_users_reconstruction_callbacks(app: object, context: UsersReconstructionWebContext) -> None:
    @app.callback(
        Output(_id('inspection-result'), 'children'),
        Output(_id('inspection'), 'data'),
        Input(_id('inspect'), 'n_clicks'),
        prevent_initial_call=True,
    )
    def inspect(clicks):
        if not clicks or not context.can_manage():
            return no_update, no_update
        try:
            document = inspection_document(context.workflow.inspect())
            return _notice(_summary('Inspección', document)), document
        except Exception:
            _LOGGER.exception('Users reconstruction inspection failed')
            return _error('Users reconstruction inspection failed'), None

    # Se vuelve a inspeccionar en el servidor antes de ejecutar; el navegador nunca envía usuarios como autoridad.
    @app.callback(
        Output(_id('apply-result'), 'children'),
        Output(_id('inspection'), 'data', allow_duplicate=True),
        Input(_id('apply'), 'n_clicks'),
        State(_id('inspection'), 'data'),
        State(_id('confirmation'), 'value'),
        prevent_initial_call=True,
    )
    def apply(clicks, document, confirmation):
        if not clicks or not context.can_manage():
            return no_update, no_update
        if not isinstance(document, dict) or 'confirmed' not in (confirmation or ()):
            return _error('Inspect and confirm before reconstruction'), no_update
        try:
            fresh = context.workflow.inspect()
            if inspection_document(fresh) != document:
                raise UsersReconstructionConflictError('Users reconstruction inspection changed')
            if not fresh.has_changes:
                return _notice('Users runtime is already aligned'), None
            context.workflow.apply(fresh)
            return _notice(_summary(context.complete_label, document)), None
        except UsersReconstructionConflictError as error:
            return _error(str(error)), None
        except Exception:
            _LOGGER.exception('Users reconstruction publication failed')
            return _error('Users reconstruction publication failed'), None


def _summary(label: str, document: dict[str, object]) -> str:
    return (
        f"{label}. Crear: {len(document['create_ids'])}; "
        f"actualizar: {len(document['update_ids'])}; "
        f"deshabilitar: {len(document['disable_ids'])}."
    )


def _notice(message: str) -> object:
    return html.Div(message, className=f'{_PREFIX}__notice')


def _error(message: str) -> object:
    return html.Div(message, className=f'{_PREFIX}__error')
