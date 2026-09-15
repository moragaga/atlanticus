# Resuelve por separado los estados del lifecycle clásico y del workspace exact-source.
# Ambos comparten la misma forma de salida, pero nunca mezclan identidades de revisión.

from dataclasses import dataclass

from atlanticus.web.manager.projection import ManagerDraft, SourceVerificationResult
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace
from atlanticus.web.source.models import SourceSnapshot as ExactSourceSnapshot


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
    can_force_publish: bool
    can_discard_local: bool


def resolve_manager_lifecycle(
    *,
    draft: ManagerDraft | None,
    editor_revision: str | None,
    source_revision: str | None,
    validation_current: bool,
    source_verification: SourceVerificationResult | None,
) -> ManagerLifecycleState:
    normalized_editor_revision = _optional_revision(editor_revision)
    dirty = bool(
        normalized_editor_revision is not None
        and (draft is None or normalized_editor_revision != draft.revision)
    )
    has_local_work = draft is not None or dirty
    published = bool(draft is not None and draft.revision == source_revision)
    current_validation = bool(validation_current and not dirty and draft is not None)
    current_verification = bool(
        current_validation
        and source_verification is not None
        and source_verification.draft_revision == draft.revision
    )
    verification_publishable = bool(
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
            draft is not None and not dirty and not published and not current_validation
        ),
        can_verify_source=bool(current_validation and not published and not current_verification),
        can_publish=bool(verification_publishable and not published),
        can_force_publish=bool(current_validation and conflict),
        can_discard_local=bool(dirty or (draft is not None and not published)),
    )


def resolve_exact_source_lifecycle(
    *,
    workspace: ManagerWorkspace | None,
    editor_revision: str | None,
    source_snapshot: ExactSourceSnapshot,
    validation_current: bool,
    source_verification: ManagerSourceVerification | None,
) -> ManagerLifecycleState:
    # El source key es una frontera dura: un workspace nunca puede evaluarse contra otra fuente.
    if workspace is not None and workspace.base.source_key != source_snapshot.source_key:
        raise ValueError('Manager workspace source key does not match current source')
    normalized_editor_revision = _optional_revision(editor_revision)
    dirty = bool(
        normalized_editor_revision is not None
        and (workspace is None or normalized_editor_revision != workspace.revision)
    )
    has_local_work = workspace is not None or dirty
    # "Publicado" significa que el payload local está en su baseline y ese baseline corresponde
    # a la release publicada actual. El token CAS puede refrescarse sin cambiar esa identidad.
    published = bool(
        workspace is not None
        and not workspace.has_local_changes
        and source_snapshot.current is not None
        and _same_release(workspace.base, source_snapshot)
    )
    current_validation = bool(validation_current and not dirty and workspace is not None)
    # Para publicar, la verificación sí debe conservar el snapshot completo y su token CAS actual.
    current_verification = bool(
        current_validation
        and source_verification is not None
        and source_verification.workspace_revision == workspace.revision
        and source_verification.source == source_snapshot
    )
    verification_publishable = bool(
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
        can_publish=bool(verification_publishable and not published),
        # Exact-source todavía no define overwrite. No se degrada al force-publish basado en strings.
        can_force_publish=False,
        can_discard_local=bool(dirty or (workspace is not None and not published)),
    )


def _same_release(left: ExactSourceSnapshot, right: ExactSourceSnapshot) -> bool:
    left_release = left.current.release_ref.release_id if left.current is not None else None
    right_release = right.current.release_ref.release_id if right.current is not None else None
    return left_release == right_release


def _optional_revision(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
