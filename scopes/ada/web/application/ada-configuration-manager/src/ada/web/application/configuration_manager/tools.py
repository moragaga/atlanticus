from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dash import Input, Output, State, html, no_update

from ada.configuration.tools import ToolConfiguration
from ada.configuration.tools_lifecycle import build_tool_configuration_digest
from ada.web.configuration.tool_editor import (
    ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
    CONFIGURATION_STORE_ID,
    DRAFT_STORE_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    VALIDITY_STORE_ID,
    build_configuration_from_structure_editor,
    build_tool_configuration_editor,
    register_tool_source_editor_callbacks,
    register_tool_structure_editor_callbacks,
)
from atlanticus.web.manager import ManagerDraft
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.modules import WebModule


@dataclass(frozen=True, slots=True)
class ToolManagerWebContext:
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    result_id: object
    draft_owner_provider: Callable[[], str]
    can_manage: Callable[[], bool] = lambda: True


def build_tool_manager_configuration() -> object:
    return build_tool_configuration_editor()


def build_tool_history_preview(payload: dict[str, object]) -> object:
    configuration = ToolConfiguration.from_document(payload)
    structure = configuration.structure
    components = len(structure.components) if structure is not None else 0
    subcomponents = (
        sum(len(component.subcomponents) for component in structure.components)
        if structure is not None
        else 0
    )
    source_keys = configuration.source_consumption.source_keys
    return html.Div(
        [
            html.H4(configuration.display_name),
            html.Div(
                [
                    _history_item('Identificador', configuration.tool_key),
                    _history_item('Tipo', configuration.kind.value),
                    _history_item('Fuentes', ', '.join(source_keys) if source_keys else '—'),
                    _history_item('Componentes', str(components)),
                    _history_item('Subcomponentes', str(subcomponents)),
                ]
            ),
        ]
    )


def create_tool_manager_web_module(context: ToolManagerWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_tool_source_editor_callbacks(app)
        register_tool_structure_editor_callbacks(app)
        register_tool_manager_callbacks(app, context)

    return WebModule(
        name='ada-configuration-manager-tools',
        asset_layers=(ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,),
        register_callbacks=register_callbacks,
    )


def register_tool_manager_callbacks(app: object, context: ToolManagerWebContext) -> None:
    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_manager_draft(draft_data: dict[str, object] | None):
        if draft_data is None:
            return None
        try:
            draft = _owned_draft(
                draft_data,
                owner_subject_id=context.draft_owner_provider(),
            )
            configuration = ToolConfiguration.from_document(draft.payload)
        except ManagerProjectionError, ValueError:
            return None
        return configuration.to_document()

    @app.callback(
        Output(context.editor_revision_store_id, 'data', allow_duplicate=True),
        Input(DRAFT_STORE_ID, 'data'),
        Input(VALIDITY_STORE_ID, 'data'),
        Input(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        Input(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(
        source_document: dict[str, object] | None,
        source_valid: bool | None,
        structure_document: dict[str, object] | None,
        structure_valid: bool | None,
    ):
        if source_valid is not True or structure_valid is not True:
            return 'invalid'
        if not isinstance(source_document, dict) or not isinstance(structure_document, dict):
            return 'invalid'
        try:
            configuration = _editor_configuration(
                source_document=source_document,
                structure_document=structure_document,
            )
        except ValueError:
            return 'invalid'
        return build_tool_configuration_digest(configuration)

    @app.callback(
        Output(context.result_id, 'children', allow_duplicate=True),
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(DRAFT_STORE_ID, 'data'),
        State(VALIDITY_STORE_ID, 'data'),
        State(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        State(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_tool_draft(
        clicks: int | None,
        source_document: dict[str, object] | None,
        source_valid: bool | None,
        structure_document: dict[str, object] | None,
        structure_valid: bool | None,
        current_draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return _error('Management access is denied'), no_update, no_update
        if (
            source_valid is not True
            or structure_valid is not True
            or not isinstance(source_document, dict)
            or not isinstance(structure_document, dict)
        ):
            return _error('Tool editor must be valid before saving'), no_update, no_update
        try:
            configuration = _editor_configuration(
                source_document=source_document,
                structure_document=structure_document,
            )
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
                raise ManagerProjectionError('Tool editor revision changed before draft save')
        except (ManagerProjectionError, ValueError) as error:
            return _error(str(error)), no_update, no_update
        document = draft.to_document()
        return None, document, document


def _editor_configuration(
    *,
    source_document: dict[str, object],
    structure_document: dict[str, object],
) -> ToolConfiguration:
    source_configuration = ToolConfiguration.from_document(source_document)
    return build_configuration_from_structure_editor(
        base_configuration=source_configuration,
        structure_document=structure_document,
    )


def _owned_draft(
    data: dict[str, object],
    *,
    owner_subject_id: str,
) -> ManagerDraft:
    draft = ManagerDraft.from_document(data)
    if draft.owner_subject_id != owner_subject_id.strip():
        raise ManagerProjectionError('Browser draft belongs to another user')
    return draft


def _history_item(label: str, value: str) -> object:
    return html.Div([html.Small(label), html.Strong(value)])


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0
