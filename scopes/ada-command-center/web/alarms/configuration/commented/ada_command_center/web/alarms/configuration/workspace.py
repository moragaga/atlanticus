from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from ada_command_center.web.alarms.configuration.tool_dependencies import (
    pin_workspace_tool_catalog_revision,
)
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceCatalog
from ada_command_center.web.alarms.configuration.workflows import (
    AlarmConfigurationManagerSourceWorkflow,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspace

AlarmConfigurationManagerPrincipalProvider = Callable[[], ManagerPrincipal]
AlarmConfigurationToolReferenceProvider = Callable[[], AlarmToolReferenceCatalog | None]


# Mantiene la especialización Alarm encima del Manager genérico sin modificar sus contratos.
class AlarmConfigurationManagerWorkspaceBinding:
    def __init__(
        self,
        *,
        source: AlarmConfigurationManagerSourceWorkflow,
        principal_provider: AlarmConfigurationManagerPrincipalProvider,
        tool_reference_provider: AlarmConfigurationToolReferenceProvider,
    ) -> None:
        self._source = source
        self._principal_provider = principal_provider
        self._tool_reference_provider = tool_reference_provider

    def load_payload(
        self,
        document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if document is None:
            return None
        workspace = self._require_workspace(document)
        return deepcopy(workspace.payload)

    def save_payload(
        self,
        document: dict[str, object] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        # Cada Save Draft adopta la revisión Tools current y la incorpora al hash del workspace.
        tool_references = self._tool_reference_provider()
        if tool_references is None:
            raise ManagerProjectionError(
                'Confirmed Tool Catalog is required before saving Alarm Configuration'
            )
        pinned_payload = pin_workspace_tool_catalog_revision(
            payload,
            tool_references.catalog_revision,
        )
        principal = self._principal_provider()
        if document is None:
            workspace = ManagerWorkspace.create(
                owner_subject_id=principal.subject_id,
                payload=pinned_payload,
                base=self._source.get_source_snapshot(),
            )
            return workspace.to_document()
        workspace = self._require_workspace(document)
        return workspace.with_payload(pinned_payload).to_document()

    def _require_workspace(self, document: dict[str, object]) -> ManagerWorkspace:
        try:
            workspace = ManagerWorkspace.from_document(document)
        except ValueError as error:
            raise ManagerProjectionError(
                'Alarm Configuration browser workspace is invalid'
            ) from error
        principal = self._principal_provider()
        if workspace.owner_subject_id != principal.subject_id:
            raise ManagerProjectionError(
                'Alarm Configuration browser workspace belongs to another user'
            )
        if workspace.base.source_key != self._source.source_key:
            raise ManagerProjectionError(
                'Alarm Configuration browser workspace belongs to another source'
            )
        return workspace
