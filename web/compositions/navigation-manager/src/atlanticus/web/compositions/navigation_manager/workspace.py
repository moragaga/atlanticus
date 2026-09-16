from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from atlanticus.web.compositions.navigation_manager.workflows import (
    NavigationManagerSourceWorkflow,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspace

NavigationManagerPrincipalProvider = Callable[[], ManagerPrincipal]


class NavigationManagerWorkspaceBinding:
    def __init__(
        self,
        *,
        source: NavigationManagerSourceWorkflow,
        principal_provider: NavigationManagerPrincipalProvider,
    ) -> None:
        self._source = source
        self._principal_provider = principal_provider

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
        principal = self._principal_provider()
        if document is None:
            workspace = ManagerWorkspace.create(
                owner_subject_id=principal.subject_id,
                payload=payload,
                base=self._source.get_source_snapshot(),
            )
            return workspace.to_document()
        workspace = self._require_workspace(document)
        return workspace.with_payload(payload).to_document()

    def _require_workspace(self, document: dict[str, object]) -> ManagerWorkspace:
        try:
            workspace = ManagerWorkspace.from_document(document)
        except ValueError as error:
            raise ManagerProjectionError('Browser workspace is invalid') from error
        principal = self._principal_provider()
        if workspace.owner_subject_id != principal.subject_id:
            raise ManagerProjectionError('Browser workspace belongs to another user')
        if workspace.base.source_key != self._source.source_key:
            raise ManagerProjectionError('Browser workspace belongs to another source')
        return workspace
