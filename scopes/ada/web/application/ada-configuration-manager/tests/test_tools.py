import base64
import json

from ada.web.application.configuration_manager.tools import (
    TOOL_IMPORT_UPLOAD_ID,
    TOOL_MANAGER_ROOT_ID,
    TOOL_SAVE_BUTTON_ID,
    ToolManagerWebContext,
    _decode_tool_configuration_import,
    _editor_configuration,
    build_tool_manager_configuration,
    register_tool_manager_callbacks,
)
from ada.web.application.configuration_manager.workspace import ManagerWorkspaceBridge
from atlanticus.web.manager import ManagerWorkspace, build_workspace_revision
from atlanticus.web.source.models import SourceKey, SourceSnapshot


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
        'source_consumption': {'tool_key': 'process', 'source_keys': ['pi']},
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
    snapshot = SourceSnapshot(SourceKey('tools'), None, None)
    bridge = ManagerWorkspaceBridge(
        owner_subject_id_provider=lambda: 'local',
        source_snapshot_provider=lambda: snapshot,
    )
    return ToolManagerWebContext(
        workspace_payload_reader=bridge.read_payload,
        workspace_payload_writer=bridge.write_payload,
        draft_store_id={'type': 'draft', 'module': 'tools'},
        saved_draft_store_id={'type': 'saved', 'module': 'tools'},
        draft_save_action_id={'type': 'action', 'module': 'tools'},
        editor_revision_store_id={'type': 'editor', 'module': 'tools'},
        result_id={'type': 'result', 'module': 'tools'},
        source_name='Source',
        projection_name='Projection',
    )


def upload_contents(document: dict[str, object]) -> str:
    payload = json.dumps(document).encode('utf-8')
    return f"data:application/json;base64,{base64.b64encode(payload).decode('ascii')}"


def test_tool_manager_keeps_existing_editor_surface_and_controls() -> None:
    layout = build_tool_manager_configuration(tool_context())
    serialized = repr(layout)

    assert layout.id == TOOL_MANAGER_ROOT_ID
    assert TOOL_IMPORT_UPLOAD_ID in serialized
    assert TOOL_SAVE_BUTTON_ID in serialized


def test_tool_import_decodes_canonical_configuration() -> None:
    configuration = _decode_tool_configuration_import(upload_contents(tool_document()))

    assert configuration.tool_key == 'process'
    assert configuration.structure is not None
    assert configuration.structure.component('crusher').display_name == 'Chancado'


def test_tool_save_writes_manager_workspace() -> None:
    app = CallbackApp()
    context = tool_context()
    register_tool_manager_callbacks(app, context)
    document = tool_document()
    configuration = _editor_configuration(
        source_document=document,
        structure_document=document['structure'],
    )
    revision = build_workspace_revision(configuration.to_document())

    _, local_result, draft_data, saved_draft_data = app.callbacks['save_tool_draft'](
        1,
        None,
        document,
        True,
        document['structure'],
        True,
        None,
        revision,
    )

    assert local_result is not None
    assert draft_data == saved_draft_data
    workspace = ManagerWorkspace.from_document(draft_data)
    assert workspace.owner_subject_id == 'local'
    assert workspace.payload['tool_key'] == 'process'
    assert workspace.base.source_key == SourceKey('tools')
