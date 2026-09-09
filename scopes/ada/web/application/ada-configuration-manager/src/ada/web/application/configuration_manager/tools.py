from __future__ import annotations

import base64
import json
from binascii import Error as BinasciiError
from collections.abc import Callable
from dataclasses import dataclass

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from ada.configuration.tools import ToolConfiguration
from ada.configuration.tools_lifecycle import build_tool_configuration_digest
from ada.web.configuration.tool_editor import (
    ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
    BRANDING_ID,
    CONFIGURATION_STORE_ID,
    COVERAGE_ID,
    DISPATCH_DEGRADATION_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_PREVENTIVE_ID,
    DISPLAY_NAME_ID,
    DRAFT_STORE_ID,
    KIND_ID,
    PI_DEGRADATION_ID,
    PI_PREVENTIVE_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    VALIDITY_STORE_ID,
    build_configuration_from_structure_editor,
    build_tool_configuration_editor,
    register_tool_source_editor_callbacks,
    register_tool_structure_editor_callbacks,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_SCOPE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
)
from atlanticus.web.assets import AssetLayer
from atlanticus.web.manager import ManagerDraft
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.modules import WebModule

TOOL_MANAGER_ROOT_ID = 'ada-configuration-manager-tools'
TOOL_SOURCE_NAME_ID = 'ada-configuration-manager-tools-source-name'
TOOL_PROJECTION_NAME_ID = 'ada-configuration-manager-tools-projection-name'
TOOL_IMPORT_UPLOAD_ID = 'ada-configuration-manager-tools-import'
TOOL_IMPORT_RESULT_ID = 'ada-configuration-manager-tools-import-result'
TOOL_SAVE_BUTTON_ID = 'ada-configuration-manager-tools-save-draft'
TOOL_SAVE_RESULT_ID = 'ada-configuration-manager-tools-save-result'
TOOL_DETAIL_SECTION_ID = 'ada-configuration-manager-tools-detail-section'
TOOL_DETAIL_BUTTON_ID = 'ada-configuration-manager-tools-detail-open'
TOOL_DETAIL_MODAL_ID = 'ada-configuration-manager-tools-detail-modal'
TOOL_DETAIL_BACKDROP_ID = 'ada-configuration-manager-tools-detail-backdrop'
TOOL_DETAIL_CLOSE_ID = 'ada-configuration-manager-tools-detail-close'
TOOL_DETAIL_BODY_ID = 'ada-configuration-manager-tools-detail-body'

_TOOL_DETAIL_MODAL_CLOSED = 'ada-configuration-manager-tools__modal'
_TOOL_DETAIL_MODAL_OPEN = (
    'ada-configuration-manager-tools__modal '
    'ada-configuration-manager-tools__modal--open'
)

TOOL_MANAGER_ASSET_LAYER = AssetLayer(
    name='ada_configuration_manager_tools',
    load_order=720,
    package='ada.web.application.configuration_manager',
)


@dataclass(frozen=True, slots=True)
class ToolManagerWebContext:
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    result_id: object
    draft_owner_provider: Callable[[], str]
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'


def build_tool_manager_configuration(context: ToolManagerWebContext) -> object:
    return html.Div(
        [
            _tool_runtime_context(context),
            build_tool_configuration_editor(),
            _tool_detail_section(),
            _tool_save_section(),
            _tool_detail_modal(),
        ],
        id=TOOL_MANAGER_ROOT_ID,
        className='ada-configuration-manager-tools atlanticus-bootstrap',
    )


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
        asset_layers=(
            ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
            TOOL_MANAGER_ASSET_LAYER,
        ),
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
        except (ManagerProjectionError, ValueError):
            return None
        return configuration.to_document()

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(TOOL_IMPORT_RESULT_ID, 'children'),
        Input(TOOL_IMPORT_UPLOAD_ID, 'contents'),
        prevent_initial_call=True,
    )
    def import_tool_configuration(contents: str | None):
        if contents is None:
            return no_update, no_update
        if not context.can_manage():
            return no_update, _error('Management access is denied')
        try:
            configuration = _decode_tool_configuration_import(contents)
        except ValueError as error:
            return no_update, _error(str(error))
        return configuration.to_document(), _success('Configuración importada en el editor.')

    @app.callback(
        Output(TOOL_DETAIL_MODAL_ID, 'className'),
        Output(TOOL_DETAIL_BODY_ID, 'children'),
        Input(TOOL_DETAIL_BUTTON_ID, 'n_clicks'),
        Input(TOOL_DETAIL_CLOSE_ID, 'n_clicks'),
        Input(TOOL_DETAIL_BACKDROP_ID, 'n_clicks'),
        State(DISPLAY_NAME_ID, 'value'),
        State(KIND_ID, 'value'),
        State(COVERAGE_ID, 'value'),
        State(BRANDING_ID, 'value'),
        State(PI_PREVENTIVE_ID, 'value'),
        State(PI_DEGRADATION_ID, 'value'),
        State(DISPATCH_ENABLED_ID, 'value'),
        State(DISPATCH_PREVENTIVE_ID, 'value'),
        State(DISPATCH_DEGRADATION_ID, 'value'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'data'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'data',
        ),
        State(
            {
                'type': SUBCOMPONENT_DISPLAY_NAME_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_DISPLAY_NAME_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        State(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        State(DRAFT_STORE_ID, 'data'),
        State(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def show_tool_detail(
        open_clicks: int | None,
        close_clicks: int | None,
        backdrop_clicks: int | None,
        display_name: str | None,
        kind_value: str | None,
        coverage: str | None,
        branding: str | None,
        pi_preventive: int | float | None,
        pi_degradation: int | float | None,
        dispatch_values: list[str] | None,
        dispatch_preventive: int | float | None,
        dispatch_degradation: int | float | None,
        component_key_ids: list[dict[str, object]],
        component_keys: list[object],
        component_name_ids: list[dict[str, object]],
        component_names: list[object],
        component_scope_ids: list[dict[str, object]],
        component_scopes: list[object],
        subcomponent_key_ids: list[dict[str, object]],
        subcomponent_keys: list[object],
        subcomponent_name_ids: list[dict[str, object]],
        subcomponent_names: list[object],
        subcomponent_linked_ids: list[dict[str, object]],
        subcomponent_links: list[object],
        source_document: dict[str, object] | None,
        structure_document: dict[str, object] | None,
    ):
        del close_clicks, backdrop_clicks
        if ctx.triggered_id in {TOOL_DETAIL_CLOSE_ID, TOOL_DETAIL_BACKDROP_ID}:
            return _TOOL_DETAIL_MODAL_CLOSED, no_update
        if ctx.triggered_id != TOOL_DETAIL_BUTTON_ID or not _click_is_real(open_clicks):
            return no_update, no_update
        snapshot = _tool_detail_snapshot(
            display_name=display_name,
            kind_value=kind_value,
            coverage=coverage,
            branding=branding,
            pi_preventive=pi_preventive,
            pi_degradation=pi_degradation,
            dispatch_values=dispatch_values,
            dispatch_preventive=dispatch_preventive,
            dispatch_degradation=dispatch_degradation,
            component_key_ids=component_key_ids,
            component_keys=component_keys,
            component_name_ids=component_name_ids,
            component_names=component_names,
            component_scope_ids=component_scope_ids,
            component_scopes=component_scopes,
            subcomponent_key_ids=subcomponent_key_ids,
            subcomponent_keys=subcomponent_keys,
            subcomponent_name_ids=subcomponent_name_ids,
            subcomponent_names=subcomponent_names,
            subcomponent_linked_ids=subcomponent_linked_ids,
            subcomponent_links=subcomponent_links,
            source_document=source_document,
            structure_document=structure_document,
        )
        return _TOOL_DETAIL_MODAL_OPEN, _render_tool_detail(snapshot)

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
        Output(TOOL_SAVE_RESULT_ID, 'children'),
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Input(TOOL_SAVE_BUTTON_ID, 'n_clicks'),
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
        local_clicks: int | None,
        workflow_clicks: int | None,
        source_document: dict[str, object] | None,
        source_valid: bool | None,
        structure_document: dict[str, object] | None,
        structure_valid: bool | None,
        current_draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not (_click_is_real(local_clicks) or _click_is_real(workflow_clicks)):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            return (
                _error('Management access is denied'),
                _error('Management access is denied'),
                no_update,
                no_update,
            )
        if (
            source_valid is not True
            or structure_valid is not True
            or not isinstance(source_document, dict)
            or not isinstance(structure_document, dict)
        ):
            return (
                _error('Tool editor must be valid before saving'),
                _error('Tool editor must be valid before saving'),
                no_update,
                no_update,
            )
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
            return _error(str(error)), _error(str(error)), no_update, no_update
        document = draft.to_document()
        return None, _success('Borrador guardado en este navegador.'), document, document


def _tool_runtime_context(context: ToolManagerWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=TOOL_SOURCE_NAME_ID),
                ],
                className='ada-configuration-manager-tools__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=TOOL_PROJECTION_NAME_ID),
                ],
                className='ada-configuration-manager-tools__runtime-source',
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=TOOL_IMPORT_UPLOAD_ID,
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
                            'Carga Tool Configuration en el editor. '
                            'No guarda, publica ni proyecta cambios.'
                        ),
                        className='ada-configuration-manager-tools__runtime-help',
                    ),
                    html.Div(id=TOOL_IMPORT_RESULT_ID),
                ],
                className='ada-configuration-manager-tools__import',
            ),
        ],
        className='ada-configuration-manager-tools__runtime-context',
    )



def _tool_detail_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Configuración resultante'),
                            html.P(
                                'Inspecciona la configuración actual del editor sin guardar, '
                                'publicar ni proyectar cambios.'
                            ),
                        ],
                        className='ada-configuration-manager-tools__section-copy',
                    ),
                    html.Button(
                        'Ver detalle',
                        id=TOOL_DETAIL_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                        className='btn btn-outline-secondary',
                    ),
                ],
                className='ada-configuration-manager-tools__section-heading',
            ),
        ],
        id=TOOL_DETAIL_SECTION_ID,
        className=(
            'ada-configuration-manager-tools__section '
            'ada-configuration-manager-tools__section--inspection'
        ),
    )


def _tool_detail_modal() -> object:
    return html.Div(
        [
            html.Button(
                id=TOOL_DETAIL_BACKDROP_ID,
                className='ada-configuration-manager-tools__modal-backdrop',
                type='button',
                **{'aria-label': 'Cerrar detalle de configuración'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.H2('Detalle de configuración'),
                                    html.P(
                                        'Vista de la configuración actual del editor. '
                                        'No modifica ni persiste información.'
                                    ),
                                ],
                                className='ada-configuration-manager-tools__modal-heading',
                            ),
                            html.Button(
                                id=TOOL_DETAIL_CLOSE_ID,
                                n_clicks=0,
                                type='button',
                                className='btn-close',
                                **{
                                    'aria-label': (
                                        'Cerrar detalle de configuración'
                                    )
                                },
                            ),
                        ],
                        className=(
                            'modal-header '
                            'ada-configuration-manager-tools__modal-header'
                        ),
                    ),
                    html.Div(
                        id=TOOL_DETAIL_BODY_ID,
                        className=(
                            'modal-body '
                            'ada-configuration-manager-tools__modal-body'
                        ),
                    ),
                ],
                className=(
                    'modal-content '
                    'ada-configuration-manager-tools__modal-dialog'
                ),
                role='dialog',
                **{'aria-modal': 'true'},
            ),
        ],
        id=TOOL_DETAIL_MODAL_ID,
        className=_TOOL_DETAIL_MODAL_CLOSED,
    )


def _tool_detail_snapshot(
    *,
    display_name: str | None,
    kind_value: str | None,
    coverage: str | None,
    branding: str | None,
    pi_preventive: int | float | None,
    pi_degradation: int | float | None,
    dispatch_values: list[str] | None,
    dispatch_preventive: int | float | None,
    dispatch_degradation: int | float | None,
    component_key_ids: list[dict[str, object]],
    component_keys: list[object],
    component_name_ids: list[dict[str, object]],
    component_names: list[object],
    component_scope_ids: list[dict[str, object]],
    component_scopes: list[object],
    subcomponent_key_ids: list[dict[str, object]],
    subcomponent_keys: list[object],
    subcomponent_name_ids: list[dict[str, object]],
    subcomponent_names: list[object],
    subcomponent_linked_ids: list[dict[str, object]],
    subcomponent_links: list[object],
    source_document: dict[str, object] | None,
    structure_document: dict[str, object] | None,
) -> dict[str, object]:
    keys_by_index = _pattern_value_map(component_key_ids, component_keys, ('index',))
    names_by_index = _pattern_value_map(component_name_ids, component_names, ('index',))
    scopes_by_index = _pattern_value_map(component_scope_ids, component_scopes, ('index',))
    component_indexes = sorted(
        {key[0] for key in (*keys_by_index, *names_by_index, *scopes_by_index)}
    )

    sub_keys = _pattern_value_map(
        subcomponent_key_ids,
        subcomponent_keys,
        ('owner_index', 'index'),
    )
    sub_names = _pattern_value_map(
        subcomponent_name_ids,
        subcomponent_names,
        ('owner_index', 'index'),
    )
    sub_links = _pattern_value_map(
        subcomponent_linked_ids,
        subcomponent_links,
        ('owner_index', 'index'),
    )
    sub_indexes = sorted({*sub_keys, *sub_names, *sub_links})

    components: list[dict[str, object]] = []
    component_name_by_key: dict[str, str] = {}
    for index in component_indexes:
        key = _optional_text(keys_by_index.get((index,)))
        name = _optional_text(names_by_index.get((index,)))
        scope = _optional_text(scopes_by_index.get((index,)))
        if key is not None:
            component_name_by_key[key] = name or key
        components.append(
            {
                'index': index,
                'key': key,
                'display_name': name,
                'scope': scope,
                'uses': ('KPI', 'Alarmas'),
                'subcomponents': [],
            }
        )

    components_by_index = {item['index']: item for item in components}
    for owner_index, sub_index in sub_indexes:
        owner = components_by_index.get(owner_index)
        if owner is None:
            continue
        raw_links = sub_links.get((owner_index, sub_index))
        links = _linked_values(raw_links)
        owner_key = _optional_text(keys_by_index.get((owner_index,)))
        owner['subcomponents'].append(
            {
                'key': _optional_text(sub_keys.get((owner_index, sub_index))),
                'display_name': _optional_text(
                    sub_names.get((owner_index, sub_index))
                ),
                'owner_component_key': owner_key,
                'linked_component_keys': links,
                'linked_component_labels': tuple(
                    component_name_by_key.get(key, key) for key in links
                ),
                'uses': ('Alarmas',),
            }
        )

    contract = None
    if isinstance(source_document, dict) and isinstance(structure_document, dict):
        try:
            contract = _editor_configuration(
                source_document=source_document,
                structure_document=structure_document,
            ).to_document()
        except ValueError:
            contract = None

    return {
        'general': {
            'display_name': _optional_text(display_name),
            'kind': _optional_text(kind_value),
            'coverage': _optional_text(coverage),
            'branding': _optional_text(branding),
        },
        'sources': {
            'pi_preventive': pi_preventive,
            'pi_degradation': pi_degradation,
            'dispatch_enabled': 'dispatch' in (dispatch_values or []),
            'dispatch_preventive': dispatch_preventive,
            'dispatch_degradation': dispatch_degradation,
        },
        'fixed_destinations': (
            {
                'key': 'global_indicators',
                'display_name': 'Indicadores globales',
                'uses': ('KPI',),
            },
            {
                'key': 'time_status',
                'display_name': 'Time Status',
                'uses': ('KPI',),
            },
        ),
        'components': components,
        'contract': contract,
    }


def _render_tool_detail(snapshot: dict[str, object]) -> object:
    general = snapshot['general']
    sources = snapshot['sources']
    components = snapshot['components']
    contract = snapshot['contract']
    return html.Div(
        [
            html.Section(
                [
                    html.H3('Qué representa esta vista'),
                    html.Div(
                        [
                            _detail_legend('KPI', 'Destino disponible para KPI Configuration.'),
                            _detail_legend(
                                'Alarmas',
                                'Destino estructural disponible para Alarm Configuration.',
                            ),
                            _detail_legend(
                                'ID interno',
                                'Identidad estable usada para enlazar configuración, stores y UI.',
                            ),
                        ],
                        className='ada-configuration-manager-tools__detail-legend',
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
            html.Section(
                [
                    html.H3('Información general'),
                    html.Div(
                        [
                            _detail_value('Herramienta', general['display_name']),
                            _detail_value('Tipo', _kind_label(general['kind'])),
                            _detail_value('Cobertura', _coverage_label(general['coverage'])),
                            _detail_value('Branding', _branding_label(general['branding'])),
                        ],
                        className='ada-configuration-manager-tools__detail-grid',
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
            html.Section(
                [
                    html.H3('Fuentes operacionales'),
                    html.Div(
                        [
                            _detail_source_card(
                                'PI',
                                'Fuente principal · obligatoria',
                                sources['pi_preventive'],
                                sources['pi_degradation'],
                            ),
                            _detail_source_card(
                                'Dispatch',
                                (
                                    'Participa en el estado operacional'
                                    if sources['dispatch_enabled']
                                    else 'No participa'
                                ),
                                (
                                    sources['dispatch_preventive']
                                    if sources['dispatch_enabled']
                                    else None
                                ),
                                (
                                    sources['dispatch_degradation']
                                    if sources['dispatch_enabled']
                                    else None
                                ),
                            ),
                        ],
                        className='ada-configuration-manager-tools__detail-source-grid',
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
            html.Section(
                [
                    html.H3('Destinos fijos'),
                    html.P(
                        'Indicadores globales y Time Status siempre están disponibles '
                        'como destinos de configuración KPI.'
                    ),
                    html.Div(
                        [
                            _detail_destination(item)
                            for item in snapshot['fixed_destinations']
                        ],
                        className='ada-configuration-manager-tools__detail-destinations',
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
            html.Section(
                [
                    html.H3('Componentes y subcomponentes'),
                    html.P(
                        'Los componentes son destinos de KPI y Alarmas. '
                        'Los subcomponentes son destinos de Alarmas.'
                    ),
                    (
                        html.Div(
                            [_detail_component(item) for item in components],
                            className='ada-configuration-manager-tools__detail-components',
                        )
                        if components
                        else _detail_empty('No hay componentes configurados todavía.')
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
            html.Section(
                [
                    html.H3('Contrato actual'),
                    (
                        html.Details(
                            [
                                html.Summary('Ver Tool Configuration serializada'),
                                html.Pre(
                                    json.dumps(
                                        contract,
                                        ensure_ascii=False,
                                        indent=2,
                                    ),
                                    className=(
                                        'ada-configuration-manager-tools__detail-contract '
                                        'ada-configuration-manager-tools__selectable'
                                    ),
                                ),
                            ],
                            className='ada-configuration-manager-tools__detail-contract-box',
                        )
                        if contract is not None
                        else _detail_empty(
                            _contract_pending_message(
                                general=general,
                                sources=sources,
                                components=components,
                            )
                        )
                    ),
                ],
                className='ada-configuration-manager-tools__detail-section',
            ),
        ],
        className='ada-configuration-manager-tools__detail',
    )


def _detail_legend(label: str, copy: str) -> object:
    return html.Div(
        [html.Strong(label), html.Span(copy)],
        className='ada-configuration-manager-tools__detail-legend-item',
    )


def _detail_value(label: str, value: object, *, technical: bool = False) -> object:
    resolved = _display_value(value)
    display = (
        html.Code(
            resolved,
            className=(
                'ada-configuration-manager-tools__detail-code '
                'ada-configuration-manager-tools__selectable'
            ),
        )
        if technical and resolved != 'No configurado'
        else html.Strong(resolved)
    )
    return html.Div(
        [html.Small(label), display],
        className='ada-configuration-manager-tools__detail-value',
    )


def _detail_source_card(
    name: str,
    status: str,
    preventive: object,
    degradation: object,
) -> object:
    return html.Article(
        [
            html.Div(
                [html.Strong(name), html.Span(status)],
                className='ada-configuration-manager-tools__detail-card-heading',
            ),
            html.Div(
                [
                    _detail_value('Preventivo', _seconds_value(preventive)),
                    _detail_value('Degradación', _seconds_value(degradation)),
                ],
                className='ada-configuration-manager-tools__detail-grid',
            ),
        ],
        className='ada-configuration-manager-tools__detail-card',
    )


def _detail_destination(item: dict[str, object]) -> object:
    return html.Article(
        [
            html.Div(
                [
                    html.Strong(_display_value(item.get('display_name'))),
                    _detail_badges(item.get('uses')),
                ],
                className='ada-configuration-manager-tools__detail-card-heading',
            ),
            _detail_value('ID interno', item.get('key'), technical=True),
        ],
        className='ada-configuration-manager-tools__detail-card',
    )


def _detail_component(item: dict[str, object]) -> object:
    subcomponents = item.get('subcomponents') or []
    return html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(
                                _display_value(
                                    item.get('display_name'),
                                    fallback='Componente sin nombre',
                                )
                            ),
                            html.Span(_scope_label(item.get('scope'))),
                        ],
                        className='ada-configuration-manager-tools__detail-card-heading-copy',
                    ),
                    _detail_badges(item.get('uses')),
                ],
                className='ada-configuration-manager-tools__detail-card-heading',
            ),
            _detail_value('ID interno', item.get('key'), technical=True),
            (
                html.Div(
                    [_detail_subcomponent(subcomponent) for subcomponent in subcomponents],
                    className='ada-configuration-manager-tools__detail-subcomponents',
                )
                if subcomponents
                else _detail_empty('Sin subcomponentes configurados.')
            ),
        ],
        className=(
            'ada-configuration-manager-tools__detail-card '
            'ada-configuration-manager-tools__detail-card--component'
        ),
    )


def _detail_subcomponent(item: dict[str, object]) -> object:
    linked = item.get('linked_component_labels') or ()
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(
                        _display_value(
                            item.get('display_name'),
                            fallback='Subcomponente sin nombre',
                        )
                    ),
                    _detail_badges(item.get('uses')),
                ],
                className='ada-configuration-manager-tools__detail-card-heading',
            ),
            html.Div(
                [
                    _detail_value('ID interno', item.get('key'), technical=True),
                    _detail_value(
                        'Propietario',
                        item.get('owner_component_key'),
                        technical=True,
                    ),
                    _detail_value(
                        'Visible también en',
                        ', '.join(linked) if linked else None,
                    ),
                ],
                className='ada-configuration-manager-tools__detail-grid',
            ),
        ],
        className='ada-configuration-manager-tools__detail-subcomponent',
    )


def _detail_badges(values: object) -> object:
    items = tuple(values) if isinstance(values, (list, tuple)) else ()
    return html.Div(
        [
            html.Span(
                str(value),
                className='ada-configuration-manager-tools__detail-badge',
            )
            for value in items
        ],
        className='ada-configuration-manager-tools__detail-badges',
    )



def _contract_pending_message(
    *,
    general: object,
    sources: object,
    components: object,
) -> str:
    general_data = general if isinstance(general, dict) else {}
    sources_data = sources if isinstance(sources, dict) else {}
    component_items = (
        tuple(item for item in components if isinstance(item, dict))
        if isinstance(components, (list, tuple))
        else ()
    )

    kind = _optional_text(general_data.get('kind'))
    coverage = _optional_text(general_data.get('coverage'))

    if kind is None:
        return 'No configurado. Selecciona primero el tipo de herramienta.'
    if kind == 'process' and coverage not in {'mine', 'plant'}:
        return 'Pendiente de completar. Procesos requiere cobertura Mina o Planta.'
    if not component_items:
        return 'Pendiente de completar. Agrega al menos un componente.'
    if any(not item.get('subcomponents') for item in component_items):
        return (
            'Pendiente de completar. Cada componente requiere al menos '
            'un subcomponente.'
        )

    if kind == 'integrated_operations':
        scopes = {
            scope
            for item in component_items
            if (scope := _optional_text(item.get('scope'))) is not None
        }
        if not {'mine', 'plant'}.issubset(scopes):
            return (
                'Pendiente de completar. Operaciones integradas requiere '
                'componentes de Mina y Planta.'
            )

        scope_by_key = {
            key: _optional_text(item.get('scope'))
            for item in component_items
            if (key := _optional_text(item.get('key'))) is not None
        }
        for owner in component_items:
            owner_scope = _optional_text(owner.get('scope'))
            subcomponents = owner.get('subcomponents')
            if not isinstance(subcomponents, list):
                continue
            for subcomponent in subcomponents:
                if not isinstance(subcomponent, dict):
                    continue
                links = subcomponent.get('linked_component_keys')
                if not isinstance(links, (list, tuple)):
                    continue
                if any(
                    scope_by_key.get(str(link)) not in {None, owner_scope}
                    for link in links
                ):
                    return (
                        'Pendiente de completar. Visible también en sólo puede '
                        'enlazar componentes del mismo ámbito.'
                    )

    if sources_data.get('pi_preventive') is None:
        return 'Pendiente de completar. Configura el umbral preventivo de PI.'
    if sources_data.get('pi_degradation') is None:
        return 'Pendiente de completar. Configura el umbral de degradación de PI.'
    if bool(sources_data.get('dispatch_enabled')):
        if sources_data.get('dispatch_preventive') is None:
            return (
                'Pendiente de completar. Configura el umbral preventivo '
                'de Dispatch.'
            )
        if sources_data.get('dispatch_degradation') is None:
            return (
                'Pendiente de completar. Configura el umbral de degradación '
                'de Dispatch.'
            )

    return (
        'Pendiente de completar. La configuración actual todavía no forma '
        'un contrato válido.'
    )

def _detail_empty(message: str) -> object:
    return html.Div(
        message,
        className='ada-configuration-manager-tools__detail-empty',
    )


def _pattern_value_map(
    ids: list[dict[str, object]],
    values: list[object],
    fields: tuple[str, ...],
) -> dict[tuple[int, ...], object]:
    resolved: dict[tuple[int, ...], object] = {}
    for component_id, value in zip(ids or [], values or [], strict=False):
        if not isinstance(component_id, dict):
            continue
        try:
            key = tuple(int(component_id[field]) for field in fields)
        except (KeyError, TypeError, ValueError):
            continue
        resolved[key] = value
    return resolved


def _linked_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        text
        for item in value
        if (text := _optional_text(item)) is not None
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display_value(
    value: object,
    *,
    fallback: str = 'No configurado',
) -> str:
    return _optional_text(value) or fallback


def _seconds_value(value: object) -> str | None:
    if value is None:
        return None
    return f'{value} s'


def _kind_label(value: object) -> str | None:
    return {
        'process': 'Procesos',
        'integrated_operations': 'Operaciones integradas',
    }.get(_optional_text(value) or '')


def _coverage_label(value: object) -> str | None:
    return {
        'mine': 'Mina',
        'plant': 'Planta',
        'mine_plant': 'Mina y Planta',
    }.get(_optional_text(value) or '')


def _scope_label(value: object) -> str:
    return _coverage_label(value) or 'Ámbito no configurado'


def _branding_label(value: object) -> str | None:
    return {
        'original': 'Normal',
        'fiestas_patrias': 'Fiestas Patrias',
        'mining_month': 'Mes de la Minería',
        'christmas': 'Navidad',
        'new_year': 'Año Nuevo',
    }.get(_optional_text(value) or '')

def _tool_save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · herramienta'),
                            html.P(
                                'Guarda la configuración actual en este navegador. '
                                'Validar, publicar y proyectar se realiza en Estado y trazabilidad.'
                            ),
                        ],
                        className='ada-configuration-manager-tools__section-copy',
                    ),
                    html.Button(
                        'Guardar borrador',
                        id=TOOL_SAVE_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                        className='btn btn-primary',
                    ),
                ],
                className='ada-configuration-manager-tools__section-heading',
            ),
            html.Div(id=TOOL_SAVE_RESULT_ID),
        ],
        className=(
            'ada-configuration-manager-tools__section '
            'ada-configuration-manager-tools__section--footer'
        ),
    )


def _decode_tool_configuration_import(contents: str) -> ToolConfiguration:
    if ',' not in contents:
        raise ValueError('Configuration file payload is invalid')
    try:
        payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
        document = json.loads(payload)
    except (BinasciiError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Configuration file payload is invalid') from error
    if not isinstance(document, dict):
        raise ValueError('Tool Configuration contract is invalid')
    return ToolConfiguration.from_document(document)


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
