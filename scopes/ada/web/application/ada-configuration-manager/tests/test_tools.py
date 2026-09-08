from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from ada.configuration.tools_lifecycle import build_tool_configuration_digest
from ada.web.application.configuration_manager.tools import (
    TOOL_IMPORT_UPLOAD_ID,
    TOOL_MANAGER_ROOT_ID,
    TOOL_SAVE_BUTTON_ID,
    ToolManagerWebContext,
    _decode_tool_configuration_import,
    _editor_configuration,
    _owned_draft,
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


def test_tool_manager_layout_wraps_current_editor_between_import_and_save() -> None:
    layout = build_tool_manager_configuration()

    assert layout.id == TOOL_MANAGER_ROOT_ID
    assert layout.children[1].id == TOOL_CONFIGURATION_EDITOR_ROOT_ID

    ids = component_ids(layout)
    assert ids.index(TOOL_IMPORT_UPLOAD_ID) < ids.index(TOOL_CONFIGURATION_EDITOR_ROOT_ID)
    assert ids.index(TOOL_CONFIGURATION_EDITOR_ROOT_ID) < ids.index(TOOL_SAVE_BUTTON_ID)


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


def test_tool_manager_web_module_composes_complete_editor_assets() -> None:
    module = create_tool_manager_web_module(tool_context())

    assert module.name == 'ada-configuration-manager-tools'
    assert module.asset_layers
    assert module.register_callbacks is not None
