# El contexto Web recibe funciones explícitas para workspace, Profiles y autorización.
# La UI no crea stores ni descubre infraestructura por su cuenta.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.profiles.models import ProfileCatalog

AdaAccessWorkspacePayloadReader = Callable[
    [dict[str, object] | None],
    dict[str, object] | None,
]
AdaAccessWorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]
AdaAccessProfileCatalogProvider = Callable[[], ProfileCatalog | None]


@dataclass(frozen=True, slots=True)
class AdaAccessAdminWebContext:
    workspace_payload_reader: AdaAccessWorkspacePayloadReader
    workspace_payload_writer: AdaAccessWorkspacePayloadWriter
    profile_catalog_provider: AdaAccessProfileCatalogProvider
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'ADA Access Source'
    projection_name: str = 'ADA Access Projection'
