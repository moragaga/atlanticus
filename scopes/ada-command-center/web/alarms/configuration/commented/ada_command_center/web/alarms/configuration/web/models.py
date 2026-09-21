# Contexto explícito que conecta la UI del dominio con el workspace genérico de Manager.
# Las funciones lectoras/escritoras evitan acoplar la UI al storage o al shell.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

AlarmConfigurationWorkspacePayloadReader = Callable[
    [dict[str, object] | None],
    dict[str, object] | None,
]
AlarmConfigurationWorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]


@dataclass(frozen=True, slots=True)
class AlarmConfigurationAdminWebContext:
    workspace_payload_reader: AlarmConfigurationWorkspacePayloadReader
    workspace_payload_writer: AlarmConfigurationWorkspacePayloadWriter
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'
