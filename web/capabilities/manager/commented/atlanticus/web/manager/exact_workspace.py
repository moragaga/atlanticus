from __future__ import annotations

# Controlador exact-source independiente de Dash. Trabaja siempre con el envelope schema 2
# y conserva el documento raw para no perder metadata que pertenece al dominio.

from copy import deepcopy
from dataclasses import dataclass

from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import ManagerProjectionError, ManagerSourceConflictError
from atlanticus.web.manager.exact_source import ExactSourcePublicationResult, ExactSourceReadResult
from atlanticus.web.manager.lifecycle import ManagerLifecycleState, resolve_exact_source_lifecycle
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.projection import DraftValidationResult
from atlanticus.web.manager.workspace import (
    ManagerSourceVerification,
    ManagerWorkspace,
    rebase_workspace_document,
    verify_workspace_source,
)


@dataclass(frozen=True, slots=True)
class ManagerExactWorkspaceState:
    workspace: ManagerWorkspace | None
    source: ExactSourceReadResult
    verification: ManagerSourceVerification | None
    lifecycle: ManagerLifecycleState


# Centraliza las operaciones locales exact-source sin introducir conocimiento de Users.
class ManagerExactWorkspaceController:
    def __init__(self, coordinator: ManagerProjectionCoordinator) -> None:
        self._coordinator = coordinator

    def load_state(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        validation_document: dict[str, object] | None,
        verification_document: dict[str, object] | None,
        editor_revision: object,
    ) -> ManagerExactWorkspaceState:
        workspace = self.safe_workspace(workspace_document, principal)
        source = self._coordinator.load_current_source_exact(module_key, principal)
        verification = self.safe_verification(verification_document, workspace)
        lifecycle = resolve_exact_source_lifecycle(
            workspace=workspace,
            editor_revision=_optional_revision(editor_revision),
            source=source,
            validation_current=self.validation_is_current(workspace, validation_document),
            source_verification=verification,
        )
        return ManagerExactWorkspaceState(
            workspace=workspace,
            source=source,
            verification=verification,
            lifecycle=lifecycle,
        )

    def require_workspace(
        self,
        document: dict[str, object] | None,
        principal: ManagerPrincipal,
    ) -> ManagerWorkspace:
        if not isinstance(document, dict):
            raise ManagerProjectionError('An exact-source browser workspace is required')
        try:
            workspace = ManagerWorkspace.from_document(document)
        except ValueError as error:
            raise ManagerProjectionError('Exact-source browser workspace is invalid') from error
        if workspace.owner_subject_id != principal.subject_id:
            raise ManagerProjectionError('Browser workspace belongs to another user')
        return workspace

    def safe_workspace(
        self,
        document: dict[str, object] | None,
        principal: ManagerPrincipal,
    ) -> ManagerWorkspace | None:
        if document is None:
            return None
        try:
            return self.require_workspace(document, principal)
        except ManagerProjectionError:
            return None

    def validation_is_current(
        self,
        workspace: ManagerWorkspace | None,
        validation: dict[str, object] | None,
    ) -> bool:
        return bool(
            workspace is not None
            and validation
            and validation.get('draft_revision') == workspace.revision
            and validation.get('valid') is True
        )

    def safe_verification(
        self,
        document: dict[str, object] | None,
        workspace: ManagerWorkspace | None,
    ) -> ManagerSourceVerification | None:
        if workspace is None or not isinstance(document, dict):
            return None
        try:
            verification = ManagerSourceVerification.from_document(document)
        except ValueError:
            return None
        if verification.workspace_revision != workspace.revision:
            return None
        return verification

    def require_verification(
        self,
        document: dict[str, object] | None,
        workspace: ManagerWorkspace,
    ) -> ManagerSourceVerification:
        verification = self.safe_verification(document, workspace)
        if verification is None:
            raise ManagerProjectionError('A current exact source verification is required')
        return verification

    def validate(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        editor_revision: object,
    ) -> DraftValidationResult:
        workspace = self.require_workspace(workspace_document, principal)
        if _optional_revision(editor_revision) != workspace.revision:
            raise ManagerProjectionError('Current editor changes must be saved before validation')
        result = self._coordinator.validate_draft(module_key, principal, workspace.payload)
        if result.draft_revision != workspace.revision:
            raise ManagerProjectionError(
                'Validated draft revision does not match browser workspace'
            )
        return result

    def verify(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        validation_document: dict[str, object] | None,
        editor_revision: object,
    ) -> ManagerSourceVerification:
        workspace = self.require_workspace(workspace_document, principal)
        if _optional_revision(editor_revision) != workspace.revision:
            raise ManagerProjectionError('Current editor changes must be saved before verification')
        if not self.validation_is_current(workspace, validation_document):
            raise ManagerProjectionError('A successful draft validation is required')
        source = self._coordinator.get_exact_source_snapshot(module_key, principal)
        return verify_workspace_source(workspace, source)

    def publish(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        validation_document: dict[str, object] | None,
        verification_document: dict[str, object] | None,
        editor_revision: object,
    ) -> tuple[ExactSourcePublicationResult, dict[str, object]]:
        workspace = self.require_workspace(workspace_document, principal)
        if _optional_revision(editor_revision) != workspace.revision:
            raise ManagerProjectionError('Current editor changes must be saved before publication')
        if not self.validation_is_current(workspace, validation_document):
            raise ManagerProjectionError('A successful draft validation is required')
        verification = self.require_verification(verification_document, workspace)
        if not verification.publishable:
            raise ManagerSourceConflictError('Manager source verification detected a conflict')
        result = self._coordinator.publish_draft_exact(
            module_key,
            principal,
            workspace.payload,
            verification.source,
        )
        if not isinstance(workspace_document, dict):
            raise ManagerProjectionError('An exact-source browser workspace is required')
        updated = rebase_workspace_document(workspace_document, result.source.snapshot)
        return result, updated

    def refresh_verification(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        try:
            workspace = self.require_workspace(workspace_document, principal)
            source = self._coordinator.get_exact_source_snapshot(module_key, principal)
            return verify_workspace_source(workspace, source).to_document()
        except ManagerProjectionError:
            return None

    def keep_draft(
        self,
        *,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        verification_document: dict[str, object] | None,
    ) -> dict[str, object]:
        workspace = self.require_workspace(workspace_document, principal)
        verification = self.require_verification(verification_document, workspace)
        if not verification.conflict:
            raise ManagerProjectionError('Manager workspace does not have a source conflict')
        if not isinstance(workspace_document, dict):
            raise ManagerProjectionError('An exact-source browser workspace is required')
        return rebase_workspace_document(workspace_document, verification.source)

    def replace_from_source(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        source = self._coordinator.load_current_source_exact(module_key, principal)
        return self.replace_with_source(
            principal=principal,
            workspace_document=workspace_document,
            source=source,
        )

    def replace_with_source(
        self,
        *,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        source: ExactSourceReadResult,
    ) -> dict[str, object] | None:
        if source.payload is None:
            return None
        workspace = self.require_workspace(workspace_document, principal)
        if workspace.base.source_key != source.snapshot.source_key:
            raise ManagerProjectionError('Manager workspace source key does not match current source')
        replacement = ManagerWorkspace.create(
            owner_subject_id=workspace.owner_subject_id,
            payload=source.payload,
            base=source.snapshot,
        )
        if not isinstance(workspace_document, dict):
            raise ManagerProjectionError('An exact-source browser workspace is required')
        # Sólo se sustituyen los campos que Manager posee; document_type u otra metadata
        # opaca del dominio se conserva sin reinterpretarla.
        updated = deepcopy(workspace_document)
        updated.update(replacement.to_document())
        return updated

    def source_changed(
        self,
        workspace: ManagerWorkspace,
        source: ExactSourceReadResult,
    ) -> bool:
        return _release_id(workspace.base) != _release_id(source.snapshot)


def _release_id(snapshot) -> object:
    if snapshot.current is None:
        return None
    return snapshot.current.release_ref.release_id


def _optional_revision(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
