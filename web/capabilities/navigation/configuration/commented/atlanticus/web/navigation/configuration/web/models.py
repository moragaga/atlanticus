# El contexto web recibe dependencias explícitas y nunca resuelve otra capability por sí mismo.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.navigation.configuration.profiles import NavigationProfileOptionsProvider

NavigationWorkspacePayloadReader = Callable[
    [dict[str, object] | None],
    dict[str, object] | None,
]
NavigationWorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]


@dataclass(frozen=True, slots=True)
class NavigationAdminWebContext:
    workspace_payload_reader: NavigationWorkspacePayloadReader
    workspace_payload_writer: NavigationWorkspacePayloadWriter
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    # La composición puede ofrecer opciones de perfiles; Navigation no exige ese provider.
    profile_options_provider: NavigationProfileOptionsProvider | None = None
