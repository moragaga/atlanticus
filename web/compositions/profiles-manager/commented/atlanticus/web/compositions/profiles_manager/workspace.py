from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from atlanticus.web.compositions.profiles_manager.workflows import ProfilesManagerSourceWorkflow
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspace

ProfilesManagerPrincipalProvider = Callable[[], ManagerPrincipal]


# Une la UI editable de Profiles con el documento de workspace propiedad de Manager.
class ProfilesManagerWorkspaceBinding:
    def __init__(
        self,
        *,
        source: ProfilesManagerSourceWorkflow,
        principal_provider: ProfilesManagerPrincipalProvider,
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
            # El primer save fija owner y base Source; ediciones posteriores preservan esa base.
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
