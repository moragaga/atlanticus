# Integra KPI Definition al flujo estándar de Atlanticus Manager.
from __future__ import annotations

import base64
import json
from binascii import Error as BinasciiError
from collections.abc import Callable
from dataclasses import dataclass

from dash import Input, Output, State, dcc, html, no_update

from ada.web.kpis.definition import (
    KpiDefinitionAuthorityProvider,
    KpiDefinitionConfiguration,
    KpiDefinitionValidationError,
    build_kpi_definition_digest,
)
from ada.web.kpis.definition.web import (
    KpiDefinitionEditorContext,
    build_kpi_definition_editor_surface,
    create_kpi_definition_editor_module,
)
from ada.web.kpis.definition.web.ids import CONFIGURATION_STORE_ID
from atlanticus.web.manager import ManagerDraft
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.modules import WebModule

KPI_DEFINITION_MANAGER_ROOT_ID = 'ada-configuration-manager-kpi-definitions'
KPI_DEFINITION_SOURCE_NAME_ID = 'ada-configuration-manager-kpi-definitions-source-name'
KPI_DEFINITION_PROJECTION_NAME_ID = 'ada-configuration-manager-kpi-definitions-projection-name'
KPI_DEFINITION_IMPORT_UPLOAD_ID = 'ada-configuration-manager-kpi-definitions-import'
KPI_DEFINITION_IMPORT_RESULT_ID = 'ada-configuration-manager-kpi-definitions-import-result'
KPI_DEFINITION_SAVE_BUTTON_ID = 'ada-configuration-manager-kpi-definitions-save-draft'
KPI_DEFINITION_SAVE_RESULT_ID = 'ada-configuration-manager-kpi-definitions-save-result'


@dataclass(frozen=True, slots=True)
class KpiDefinitionManagerWebContext:
    authority: KpiDefinitionAuthorityProvider
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    result_id: object
    draft_owner_provider: Callable[[], str]
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'

    def editor_context(self) -> KpiDefinitionEditorContext:
        return KpiDefinitionEditorContext(
            authority=self.authority,
            can_manage=self.can_manage,
        )


def build_kpi_definition_manager_configuration(
    context: KpiDefinitionManagerWebContext,
) -> object:
    return html.Div(
        [
            _runtime_context(context),
            build_kpi_definition_editor_surface(context.editor_context()),
            _save_section(),
        ],
        id=KPI_DEFINITION_MANAGER_ROOT_ID,
        className='ada-configuration-manager-kpis atlanticus-bootstrap',
    )


def build_kpi_definition_history_preview(payload: dict[str, object]) -> object:
    configuration = KpiDefinitionConfiguration.from_document(payload)
    field_count = sum(len(definition.fields) for definition in configuration.definitions)
    return html.Div(
        [
            html.H4('Definiciones KPI'),
            html.Div(
                [
                    _history_item(
                        'Definiciones',
                        str(len(configuration.definitions)),
                    ),
                    _history_item('Campos', str(field_count)),
                ]
            ),
        ]
    )


def create_kpi_definition_manager_web_module(
    context: KpiDefinitionManagerWebContext,
) -> WebModule:
    editor_module = create_kpi_definition_editor_module(
        context.editor_context(),
        include_configuration_asset=False,
    )

    def register_callbacks(app: object, services: object) -> None:
        if editor_module.register_callbacks is not None:
            editor_module.register_callbacks(app, services)
        register_kpi_definition_manager_callbacks(app, context)

    return WebModule(
        name='ada-configuration-manager-kpi-definitions',
        asset_layers=editor_module.asset_layers,
        register_callbacks=register_callbacks,
    )


def register_kpi_definition_manager_callbacks(
    app: object,
    context: KpiDefinitionManagerWebContext,
) -> None:
    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_manager_draft(draft_data: dict[str, object] | None):
        if draft_data is None:
            return no_update
        try:
            draft = _owned_draft(
                draft_data,
                owner_subject_id=context.draft_owner_provider(),
            )
            configuration = KpiDefinitionConfiguration.from_document(draft.payload)
        except (ManagerProjectionError, KpiDefinitionValidationError, ValueError):
            return no_update
        return configuration.to_document()

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(KPI_DEFINITION_IMPORT_RESULT_ID, 'children'),
        Input(KPI_DEFINITION_IMPORT_UPLOAD_ID, 'contents'),
        prevent_initial_call=True,
    )
    def import_kpi_definitions(contents: str | None):
        if contents is None:
            return no_update, no_update
        if not context.can_manage():
            return no_update, _error('No tienes permisos para administrar definiciones KPI.')
        try:
            configuration = _decode_import(contents)
        except ValueError as error:
            return no_update, _error(str(error))
        return (
            configuration.to_document(),
            _success('Definiciones KPI importadas en el editor.'),
        )

    @app.callback(
        Output(context.editor_revision_store_id, 'data', allow_duplicate=True),
        Input(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(configuration_data: dict[str, object] | None):
        try:
            configuration = _configuration(configuration_data)
        except ValueError:
            return 'invalid'
        return build_kpi_definition_digest(configuration)

    @app.callback(
        Output(context.result_id, 'children', allow_duplicate=True),
        Output(KPI_DEFINITION_SAVE_RESULT_ID, 'children'),
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Input(KPI_DEFINITION_SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_definition_draft(
        local_clicks: int | None,
        workflow_clicks: int | None,
        configuration_data: dict[str, object] | None,
        current_draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not (_click_is_real(local_clicks) or _click_is_real(workflow_clicks)):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            message = _error('No tienes permisos para administrar definiciones KPI.')
            return message, message, no_update, no_update

        try:
            configuration = _configuration(configuration_data)
            owner_subject_id = context.draft_owner_provider()
            current = (
                _owned_draft(
                    current_draft_data,
                    owner_subject_id=owner_subject_id,
                )
                if current_draft_data is not None
                else None
            )
            draft = ManagerDraft.create(
                owner_subject_id=owner_subject_id,
                payload=configuration.to_document(),
                base_source_revision=(
                    current.base_source_revision if current is not None else None
                ),
            )
            if editor_revision != draft.revision:
                raise ManagerProjectionError(
                    'La revisión del editor cambió antes de guardar el borrador.'
                )
        except (ManagerProjectionError, ValueError) as error:
            message = _error(str(error))
            return message, message, no_update, no_update

        document = draft.to_document()
        return (
            None,
            _success('Borrador guardado en este navegador.'),
            document,
            document,
        )


def _runtime_context(context: KpiDefinitionManagerWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(
                        context.source_name,
                        id=KPI_DEFINITION_SOURCE_NAME_ID,
                    ),
                ],
                className='ada-configuration-manager-kpis__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(
                        context.projection_name,
                        id=KPI_DEFINITION_PROJECTION_NAME_ID,
                    ),
                ],
                className='ada-configuration-manager-kpis__runtime-source',
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=KPI_DEFINITION_IMPORT_UPLOAD_ID,
                        children=html.Button(
                            'Importar',
                            type='button',
                            className='btn btn-outline-secondary',
                        ),
                        accept='.json,application/json',
                        multiple=False,
                    ),
                    html.Span(
                        (
                            'Carga definiciones KPI en el editor. '
                            'No guarda, publica ni proyecta cambios.'
                        ),
                        className='ada-configuration-manager-kpis__runtime-help',
                    ),
                    html.Div(id=KPI_DEFINITION_IMPORT_RESULT_ID),
                ],
                className='ada-configuration-manager-kpis__import',
            ),
        ],
        className='ada-configuration-manager-kpis__runtime-context',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · definiciones KPI'),
                            html.P(
                                'Guarda las definiciones actuales en este navegador. '
                                'Validar, publicar y proyectar se realiza en Estado y trazabilidad.'
                            ),
                        ],
                        className='ada-configuration-manager-kpis__section-copy',
                    ),
                    html.Button(
                        'Guardar borrador',
                        id=KPI_DEFINITION_SAVE_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                        className='btn btn-primary',
                    ),
                ],
                className='ada-configuration-manager-kpis__section-heading',
            ),
            html.Div(id=KPI_DEFINITION_SAVE_RESULT_ID),
        ],
        className=(
            'ada-configuration-manager-kpis__section '
            'ada-configuration-manager-kpis__section--footer'
        ),
    )


def _decode_import(contents: str) -> KpiDefinitionConfiguration:
    if ',' not in contents:
        raise ValueError('El archivo de definiciones no es válido.')
    try:
        payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
        document = json.loads(payload)
    except (BinasciiError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('El archivo de definiciones no es válido.') from error
    if not isinstance(document, dict):
        raise ValueError('El contrato de definiciones KPI no es válido.')
    try:
        return KpiDefinitionConfiguration.from_document(document)
    except KpiDefinitionValidationError as error:
        raise ValueError('El contrato de definiciones KPI no es válido.') from error


def _configuration(
    document: dict[str, object] | None,
) -> KpiDefinitionConfiguration:
    if not isinstance(document, dict):
        raise ValueError('Las definiciones KPI del editor no son válidas.')
    try:
        return KpiDefinitionConfiguration.from_document(document)
    except KpiDefinitionValidationError as error:
        raise ValueError('Las definiciones KPI del editor no son válidas.') from error


def _owned_draft(
    data: dict[str, object],
    *,
    owner_subject_id: str,
) -> ManagerDraft:
    draft = ManagerDraft.from_document(data)
    if draft.owner_subject_id != owner_subject_id.strip():
        raise ManagerProjectionError('El borrador pertenece a otro usuario.')
    return draft


def _history_item(label: str, value: str) -> object:
    return html.Div([html.Small(label), html.Strong(value)])


def _success(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--success',
    )


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0
