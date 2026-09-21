from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceCatalog

AlarmConfigurationWorkspacePayloadReader = Callable[
    [dict[str, object] | None],
    dict[str, object] | None,
]
AlarmConfigurationWorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]
AlarmToolReferenceProvider = Callable[[], AlarmToolReferenceCatalog | None]


@dataclass(frozen=True, slots=True)
class AlarmConfigurationAdminWebContext:
    workspace_payload_reader: AlarmConfigurationWorkspacePayloadReader
    workspace_payload_writer: AlarmConfigurationWorkspacePayloadWriter
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    tool_reference_provider: AlarmToolReferenceProvider | None = None
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'
