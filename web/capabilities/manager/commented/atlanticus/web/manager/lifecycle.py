# Espejo pedagógico del archivo productivo equivalente.
# Deriva las acciones permitidas del workspace, validación y verificación. Un cambio de token sin cambio de release no crea un conflicto funcional.
# Los comentarios no alteran la estructura ejecutable ni el comportamiento del archivo productivo.

from dataclasses import dataclass

from atlanticus.web.manager.source import SourceReadResult
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace


@dataclass(frozen=True, slots=True)
class ManagerLifecycleState:
    dirty: bool
    has_local_work: bool
    published: bool
    validation_current: bool
    verification_current: bool
    source_conflict: bool
    can_save_draft: bool
    can_validate: bool
    can_verify_source: bool
    can_publish: bool
    can_discard_local: bool


def resolve_manager_lifecycle(
    *,
    workspace: ManagerWorkspace | None,
    editor_revision: str | None,
    source: SourceReadResult,
    validation_current: bool,
    source_verification: ManagerSourceVerification | None,
) -> ManagerLifecycleState:
    source_snapshot = source.snapshot
    if workspace is not None and workspace.base.source_key != source_snapshot.source_key:
        raise ValueError('Manager workspace source key does not match current source')
    normalized_editor_revision = _optional_revision(editor_revision)
    dirty = bool(
        normalized_editor_revision is not None
        and (workspace is None or normalized_editor_revision != workspace.revision)
    )
    has_local_work = workspace is not None or dirty
    published = bool(
        workspace is not None
        and source.payload is not None
        and workspace.base.current == source_snapshot.current
        and workspace.payload == source.payload
    )
    current_validation = bool(validation_current and not dirty and workspace is not None)
    current_verification = bool(
        current_validation
        and source_verification is not None
        and source_verification.workspace_revision == workspace.revision
        and source_verification.source.current == source_snapshot.current
    )
    publishable = bool(
        current_verification and source_verification is not None and source_verification.publishable
    )
    conflict = bool(
        current_verification and source_verification is not None and source_verification.conflict
    )
    return ManagerLifecycleState(
        dirty=dirty,
        has_local_work=has_local_work,
        published=published,
        validation_current=current_validation,
        verification_current=current_verification,
        source_conflict=conflict,
        can_save_draft=dirty,
        can_validate=bool(
            workspace is not None and not dirty and not published and not current_validation
        ),
        can_verify_source=bool(current_validation and not published and not current_verification),
        can_publish=bool(publishable and not published),
        can_discard_local=bool(dirty or (workspace is not None and not published)),
    )


def _optional_revision(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
