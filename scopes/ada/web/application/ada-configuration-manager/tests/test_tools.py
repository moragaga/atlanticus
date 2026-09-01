from __future__ import annotations

from datetime import UTC, datetime

from ada.configuration.tools_lifecycle import build_tool_configuration_digest
from ada.web.application.configuration_manager.tools import (
    ToolManagerWebContext,
    _editor_configuration,
    _owned_draft,
    build_tool_history_preview,
    build_tool_manager_configuration,
    create_tool_manager_web_module,
)
from ada.web.configuration.tool_editor import TOOL_CONFIGURATION_EDITOR_ROOT_ID
from atlanticus.web.manager import ManagerDraft


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


def test_tool_manager_layout_composes_complete_tool_editor() -> None:
    layout = build_tool_manager_configuration()

    assert layout.id == TOOL_CONFIGURATION_EDITOR_ROOT_ID


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
    context = ToolManagerWebContext(
        draft_store_id={'type': 'draft', 'module': 'tools'},
        saved_draft_store_id={'type': 'saved', 'module': 'tools'},
        draft_save_action_id={'type': 'action', 'module': 'tools'},
        editor_revision_store_id={'type': 'editor', 'module': 'tools'},
        result_id={'type': 'result', 'module': 'tools'},
        draft_owner_provider=lambda: 'local',
    )

    module = create_tool_manager_web_module(context)

    assert module.name == 'ada-configuration-manager-tools'
    assert module.asset_layers
    assert module.register_callbacks is not None
