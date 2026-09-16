# Espejo pedagógico: traduce el payload de cada editor al ManagerWorkspace genérico sin alterar la identidad de Source.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.manager import ManagerProjectionError, ManagerWorkspace
from atlanticus.web.source.models import SourceSnapshot

WorkspacePayloadReader = Callable[[dict[str, object] | None], dict[str, object] | None]
WorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]


# Esta frontera permite que cada editor conozca sólo payloads; la identidad de Source queda en ManagerWorkspace.
class ManagerWorkspaceBridge:
    def __init__(
        self,
        *,
        owner_subject_id_provider: Callable[[], str],
        source_snapshot_provider: Callable[[], SourceSnapshot],
    ) -> None:
        self._owner_subject_id_provider = owner_subject_id_provider
        self._source_snapshot_provider = source_snapshot_provider

    def read_payload(
        self,
        document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if document is None:
            return None
        return dict(self._owned_workspace(document).payload)

    # Al guardar se conserva el SourceSnapshot base; sólo cambia el contenido local del workspace.
    def write_payload(
        self,
        document: dict[str, object] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if document is None:
            workspace = ManagerWorkspace.create(
                owner_subject_id=self._owner_subject_id(),
                payload=payload,
                base=self._source_snapshot_provider(),
            )
        else:
            workspace = self._owned_workspace(document).with_payload(payload)
        return workspace.to_document()

    def _owned_workspace(self, document: dict[str, object]) -> ManagerWorkspace:
        try:
            workspace = ManagerWorkspace.from_document(document)
        except ValueError as error:
            raise ManagerProjectionError('Browser workspace is invalid') from error
        if workspace.owner_subject_id != self._owner_subject_id():
            raise ManagerProjectionError('Browser workspace belongs to another user')
        return workspace

    def _owner_subject_id(self) -> str:
        owner = self._owner_subject_id_provider().strip()
        if not owner:
            raise ManagerProjectionError('Manager workspace owner must not be empty')
        return owner
