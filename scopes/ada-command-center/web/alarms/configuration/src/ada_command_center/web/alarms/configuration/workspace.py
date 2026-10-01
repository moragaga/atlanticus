from __future__ import annotations

from collections.abc import Callable

from ada_command_center.web.alarms.configuration.tool_dependencies import (
    pin_workspace_tool_catalog_revision,
)
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceCatalog
from ada_command_center.web.alarms.configuration.workflows import (
    AlarmConfigurationManagerSourceWorkflow,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspaceBinding

AlarmConfigurationManagerPrincipalProvider = Callable[[], ManagerPrincipal]
AlarmConfigurationToolReferenceProvider = Callable[[], AlarmToolReferenceCatalog | None]


class AlarmConfigurationManagerWorkspaceBinding:
    def __init__(
        self,
        *,
        source: AlarmConfigurationManagerSourceWorkflow,
        principal_provider: AlarmConfigurationManagerPrincipalProvider,
        tool_reference_provider: AlarmConfigurationToolReferenceProvider,
    ) -> None:
        self._workspace = ManagerWorkspaceBinding(
            owner_subject_id_provider=lambda: principal_provider().subject_id,
            source_key=source.source_key,
            source_snapshot_provider=source.get_source_snapshot,
        )
        self._tool_reference_provider = tool_reference_provider

    def load_payload(
        self,
        document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        return self._workspace.load_payload(document)

    def save_payload(
        self,
        document: dict[str, object] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        tool_references = self._tool_reference_provider()
        if tool_references is None:
            raise ManagerProjectionError(
                'Confirmed Tool Catalog is required before saving Alarm Configuration'
            )
        pinned_payload = pin_workspace_tool_catalog_revision(
            payload,
            tool_references.catalog_revision,
        )
        return self._workspace.save_payload(document, pinned_payload)
