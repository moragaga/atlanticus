from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from ada.configuration.tools import ToolConfiguration
from ada.configuration.tools_lifecycle import build_tool_configuration_digest
from ada.web.application.configuration_manager.tools import (
    TOOL_DETAIL_BUTTON_ID,
    TOOL_DETAIL_MODAL_ID,
    TOOL_DETAIL_SECTION_ID,
    TOOL_IMPORT_UPLOAD_ID,
    TOOL_MANAGER_ASSET_LAYER,
    TOOL_MANAGER_ROOT_ID,
    TOOL_PROJECTION_NAME_ID,
    TOOL_SAVE_BUTTON_ID,
    TOOL_SOURCE_NAME_ID,
    ToolManagerWebContext,
    _decode_tool_configuration_import,
    _editor_configuration,
    _owned_draft,
    _tool_detail_snapshot,
    build_tool_history_preview,
    build_tool_manager_configuration,
    create_tool_manager_web_module,
    register_tool_manager_callbacks,
)
from ada.web.configuration.tool_editor import TOOL_CONFIGURATION_EDITOR_ROOT_ID
from atlanticus.web.manager import ManagerDraft


class CallbackApp:
    def __init__(self) -> None:
        self.callbacks: dict[str, object] = {}

    def callback(self, *_args, **_kwargs):
        def register(callback):
            self.callbacks[callback.__name__] = callback
            return callback

        return register


def tool_document() -> dict[str, object]:
    return {
        'tool_key': 'process',
        'display_name': 'Operaciones Integradas',
        'kind': 'process',
        'source_consumption': {
            'tool_key': 'process',
            'source_keys': ['pi'],
        },
        'source_operational_participation': {
            'tool_key': 'process',
            'control_sources': [
                {
                    'source_key': 'pi',
                    'pre_degrading_after_seconds': 200,
                    'degrading_after_seconds': 300,
                }
            ],
            'additional_observation_source_keys': [],
        },
        'structure': {
            'tool_key': 'process',
            'kind': 'process',
            'operational_scope': 'plant',
            'components': [
                {
                    'key': 'crusher',
                    'display_name': 'Chancado',
                    'scope': None,
                    'layout_role': 'center',
                    'subcomponents': [
                        {
                            'key': 'primary',
                            'display_name': 'Primario',
                            'linked_component_keys': [],
                        }
                    ],
                }
            ],
        },
    }


def tool_context() -> ToolManagerWebContext:
    return ToolManagerWebContext(
        draft_store_id={'type': 'draft', 'module': 'tools'},
        saved_draft_store_id={'type': 'saved', 'module': 'tools'},
        draft_save_action_id={'type': 'action', 'module': 'tools'},
        editor_revision_store_id={'type': 'editor', 'module': 'tools'},
        result_id={'type': 'result', 'module': 'tools'},
        draft_owner_provider=lambda: 'local',
        source_name='SharePoint',
        projection_name='Cosmos DB',
    )


def upload_contents(document: dict[str, object]) -> str:
    payload = json.dumps(document).encode('utf-8')
    encoded = base64.b64encode(payload).decode('ascii')
    return f'data:application/json;base64,{encoded}'


def component_ids(component: object) -> list[object]:
    result: list[object] = []
    component_id = getattr(component, 'id', None)
    if component_id is not None:
        result.append(component_id)
    children = getattr(component, 'children', None)
    if children is None:
        return result
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, 'children') or getattr(child, 'id', None) is not None:
            result.extend(component_ids(child))
    return result


def component_by_id(component: object, component_id: object) -> object | None:
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if children is None:
        return None
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if not hasattr(child, 'children') and getattr(child, 'id', None) is None:
            continue
        found = component_by_id(child, component_id)
        if found is not None:
            return found
    return None


def test_tool_manager_layout_matches_existing_manager_import_and_save_pattern() -> None:
    layout = build_tool_manager_configuration(tool_context())

    assert layout.id == TOOL_MANAGER_ROOT_ID
    assert 'atlanticus-bootstrap' in layout.className
    assert layout.children[1].id == TOOL_CONFIGURATION_EDITOR_ROOT_ID

    ids = component_ids(layout)
    assert ids.index(TOOL_IMPORT_UPLOAD_ID) < ids.index(TOOL_CONFIGURATION_EDITOR_ROOT_ID)
    assert ids.index(TOOL_CONFIGURATION_EDITOR_ROOT_ID) < ids.index(TOOL_DETAIL_SECTION_ID)
    assert ids.index(TOOL_DETAIL_SECTION_ID) < ids.index(TOOL_SAVE_BUTTON_ID)
    assert TOOL_DETAIL_BUTTON_ID in ids
    assert TOOL_DETAIL_MODAL_ID in ids

    source = component_by_id(layout, TOOL_SOURCE_NAME_ID)
    projection = component_by_id(layout, TOOL_PROJECTION_NAME_ID)
    assert source is not None and source.children == 'SharePoint'
    assert projection is not None and projection.children == 'Cosmos DB'


def test_tool_import_decodes_canonical_configuration() -> None:
    configuration = _decode_tool_configuration_import(upload_contents(tool_document()))

    assert configuration.tool_key == 'process'
    assert configuration.structure is not None
    assert configuration.structure.component('crusher').display_name == 'Chancado'
    assert configuration.source_consumption.source_keys == ('pi',)


def test_tool_import_rejects_invalid_file_payload() -> None:
    with pytest.raises(ValueError, match='Configuration file payload is invalid'):
        _decode_tool_configuration_import('invalid')


def test_tool_import_callback_only_hydrates_editor_configuration() -> None:
    app = CallbackApp()
    register_tool_manager_callbacks(app, tool_context())

    configuration, result = app.callbacks['import_tool_configuration'](
        upload_contents(tool_document())
    )

    assert configuration['tool_key'] == 'process'
    assert result is not None


@pytest.mark.parametrize(
    ('local_clicks', 'workflow_clicks'),
    [(1, None), (None, 1)],
)
def test_tool_draft_save_accepts_local_and_workflow_actions(
    local_clicks: int | None,
    workflow_clicks: int | None,
) -> None:
    app = CallbackApp()
    register_tool_manager_callbacks(app, tool_context())
    document = tool_document()
    configuration = _editor_configuration(
        source_document=document,
        structure_document=document['structure'],
    )
    revision = build_tool_configuration_digest(configuration)

    _, local_result, draft_data, saved_draft_data = app.callbacks['save_tool_draft'](
        local_clicks,
        workflow_clicks,
        document,
        True,
        document['structure'],
        True,
        None,
        revision,
    )

    assert local_result is not None
    assert draft_data == saved_draft_data
    draft = ManagerDraft.from_document(draft_data)
    assert draft.owner_subject_id == 'local'
    assert draft.payload['tool_key'] == 'process'


def test_editor_revision_matches_complete_manager_draft_revision() -> None:
    document = tool_document()
    configuration = _editor_configuration(
        source_document=document,
        structure_document=document['structure'],
    )
    draft = ManagerDraft.create(
        owner_subject_id='local',
        payload=configuration.to_document(),
        base_source_revision='source',
        saved_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )

    assert build_tool_configuration_digest(configuration) == draft.revision


def test_editor_merge_preserves_structure_and_sources() -> None:
    document = tool_document()
    configuration = _editor_configuration(
        source_document=document,
        structure_document=document['structure'],
    )

    assert configuration.structure is not None
    assert configuration.structure.component('crusher').display_name == 'Chancado'
    assert configuration.source_consumption.source_keys == ('pi',)


def test_owned_draft_preserves_tool_identity_and_source_base() -> None:
    draft = ManagerDraft.create(
        owner_subject_id='local',
        payload=tool_document(),
        base_source_revision='source',
        saved_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )

    recovered = _owned_draft(draft.to_document(), owner_subject_id='local')

    assert recovered.payload['tool_key'] == 'process'
    assert recovered.base_source_revision == 'source'


def test_history_preview_is_descriptive_and_has_no_editor_selector() -> None:
    preview = build_tool_history_preview(tool_document())

    assert preview is not None


def test_tool_manager_web_module_composes_editor_and_manager_assets() -> None:
    module = create_tool_manager_web_module(tool_context())

    assert module.name == 'ada-configuration-manager-tools'
    assert TOOL_MANAGER_ASSET_LAYER in module.asset_layers
    assert module.register_callbacks is not None


def test_tool_detail_empty_state_is_neutral_and_keeps_fixed_destinations() -> None:
    snapshot = _tool_detail_snapshot(
        display_name=None,
        kind_value=None,
        coverage=None,
        branding=None,
        pi_preventive=None,
        pi_degradation=None,
        dispatch_values=[],
        dispatch_preventive=None,
        dispatch_degradation=None,
        component_key_ids=[],
        component_keys=[],
        component_name_ids=[],
        component_names=[],
        component_scope_ids=[],
        component_scopes=[],
        subcomponent_key_ids=[],
        subcomponent_keys=[],
        subcomponent_name_ids=[],
        subcomponent_names=[],
        subcomponent_linked_ids=[],
        subcomponent_links=[],
        source_document=None,
        structure_document=None,
    )

    assert snapshot['general']['display_name'] is None
    assert snapshot['components'] == []
    assert snapshot['contract'] is None
    assert [item['key'] for item in snapshot['fixed_destinations']] == [
        'global_indicators',
        'time_status',
    ]


def test_tool_detail_preserves_accents_and_structural_identity() -> None:
    document = tool_document()
    document['display_name'] = 'Operaciones Integradas – Área Húmeda'
    document['structure']['components'][0]['display_name'] = 'Chancado Primário'
    document['structure']['components'][0]['subcomponents'][0]['display_name'] = (
        'Extracción N° 1'
    )
    configuration = _editor_configuration(
        source_document=document,
        structure_document=document['structure'],
    )
    round_trip = ToolConfiguration.from_document(configuration.to_document())

    snapshot = _tool_detail_snapshot(
        display_name='Operaciones Integradas – Área Húmeda',
        kind_value='process',
        coverage='plant',
        branding='original',
        pi_preventive=200,
        pi_degradation=300,
        dispatch_values=[],
        dispatch_preventive=None,
        dispatch_degradation=None,
        component_key_ids=[{'type': 'key', 'index': 0}],
        component_keys=['crusher'],
        component_name_ids=[{'type': 'name', 'index': 0}],
        component_names=['Chancado Primário'],
        component_scope_ids=[{'type': 'scope', 'index': 0}],
        component_scopes=['plant'],
        subcomponent_key_ids=[{'type': 'sub-key', 'owner_index': 0, 'index': 0}],
        subcomponent_keys=['primary'],
        subcomponent_name_ids=[{'type': 'sub-name', 'owner_index': 0, 'index': 0}],
        subcomponent_names=['Extracción N° 1'],
        subcomponent_linked_ids=[{'type': 'sub-linked', 'owner_index': 0, 'index': 0}],
        subcomponent_links=[[]],
        source_document=document,
        structure_document=document['structure'],
    )

    assert round_trip.display_name == 'Operaciones Integradas – Área Húmeda'
    assert round_trip.structure.component('crusher').display_name == 'Chancado Primário'
    assert (
        round_trip.structure.component('crusher').subcomponent('primary').display_name
        == 'Extracción N° 1'
    )
    assert snapshot['components'][0]['key'] == 'crusher'
    assert snapshot['components'][0]['display_name'] == 'Chancado Primário'
    assert snapshot['components'][0]['subcomponents'][0]['key'] == 'primary'
    assert snapshot['components'][0]['subcomponents'][0]['display_name'] == 'Extracción N° 1'
    assert snapshot['contract']['display_name'] == 'Operaciones Integradas – Área Húmeda'
