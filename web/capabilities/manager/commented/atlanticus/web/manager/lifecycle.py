# Centraliza el estado del workspace local y diferencia trabajo local, borrador publicado y acciones permitidas.
# Cargar Source y descartar trabajo se resuelven sin mezclar publicación o proyección.

# La verificación de una fuente ausente permite la primera publicación o recreación sin mostrar un conflicto falso.
# Si existe una revisión distinta, el flujo bloquea la publicación normal hasta resolver explícitamente el conflicto.

from dataclasses import dataclass

from atlanticus.web.manager.projection import ManagerDraft, SourceVerificationResult


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


def _optional_revision(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
