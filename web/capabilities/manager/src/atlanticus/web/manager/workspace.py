from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from atlanticus.web.manager.errors import ManagerProjectionError, ManagerSourceConflictError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.projection import DraftValidationResult
from atlanticus.web.manager.source import SourcePublicationResult, SourceReadResult
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus, ProjectionTarget
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)

_SOURCE_VERIFICATION_DOCUMENT_TYPE = 'atlanticus_manager_source_verification'
_SOURCE_VERIFICATION_SCHEMA_VERSION = 2


class ManagerProjectionState(StrEnum):
    NO_SOURCE = 'no_source'
    NEVER_PROJECTED = 'never_projected'
    CURRENT = 'current'
    OUTDATED = 'outdated'


@dataclass(frozen=True, slots=True)
class ManagerWorkspace:
    owner_subject_id: str
    revision: str
    base_payload_revision: str
    saved_at_utc: datetime
    payload: dict[str, object]
    base: SourceSnapshot

    def __post_init__(self) -> None:
        owner = self.owner_subject_id.strip()
        if not owner:
            raise ValueError('Manager workspace owner must not be empty')
        expected_revision = build_workspace_revision(self.payload)
        if self.revision.strip() != expected_revision:
            raise ValueError('Manager workspace revision does not match payload')
        base_payload_revision = self.base_payload_revision.strip()
        if not base_payload_revision:
            raise ValueError('Manager workspace base payload revision must not be empty')
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise ValueError('Manager workspace timestamp must be timezone-aware')
        object.__setattr__(self, 'owner_subject_id', owner)
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'base_payload_revision', base_payload_revision)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))
        object.__setattr__(self, 'payload', deepcopy(self.payload))

    @classmethod
    def create(
        cls,
        *,
        owner_subject_id: str,
        payload: dict[str, object],
        base: SourceSnapshot,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        revision = build_workspace_revision(payload)
        return cls(
            owner_subject_id=owner_subject_id,
            revision=revision,
            base_payload_revision=revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=payload,
            base=base,
        )

    @property
    def has_local_changes(self) -> bool:
        return self.revision != self.base_payload_revision

    def with_payload(
        self,
        payload: dict[str, object],
        *,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        return ManagerWorkspace(
            owner_subject_id=self.owner_subject_id,
            revision=build_workspace_revision(payload),
            base_payload_revision=self.base_payload_revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=payload,
            base=self.base,
        )

    def rebase(
        self,
        base: SourceSnapshot,
        *,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        return ManagerWorkspace(
            owner_subject_id=self.owner_subject_id,
            revision=self.revision,
            base_payload_revision=self.revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=self.payload,
            base=base,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'schema_version': 2,
            'owner_subject_id': self.owner_subject_id,
            'revision': self.revision,
            'base_payload_revision': self.base_payload_revision,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'source_snapshot': _source_snapshot_to_document(self.base),
            'payload': deepcopy(self.payload),
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> ManagerWorkspace:
        try:
            payload = document['payload']
            source_snapshot_document = document['source_snapshot']
            if document.get('schema_version') != 2:
                raise TypeError
            if not isinstance(payload, dict) or not isinstance(source_snapshot_document, dict):
                raise TypeError
            return cls(
                owner_subject_id=str(document['owner_subject_id']),
                revision=str(document['revision']),
                base_payload_revision=str(document['base_payload_revision']),
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
                payload=deepcopy(payload),
                base=_source_snapshot_from_document(source_snapshot_document),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Manager workspace document is invalid') from error


@dataclass(frozen=True, slots=True)
class ManagerSourceVerification:
    workspace_revision: str
    base: SourceSnapshot
    source: SourceSnapshot
    checked_at_utc: datetime

    def __post_init__(self) -> None:
        workspace_revision = self.workspace_revision.strip()
        if not workspace_revision:
            raise ValueError('Manager source verification workspace revision must not be empty')
        if self.base.source_key != self.source.source_key:
            raise ValueError('Manager source verification snapshots must use the same source key')
        if self.checked_at_utc.tzinfo is None or self.checked_at_utc.utcoffset() is None:
            raise ValueError('Manager source verification timestamp must be timezone-aware')
        object.__setattr__(self, 'workspace_revision', workspace_revision)
        object.__setattr__(self, 'checked_at_utc', self.checked_at_utc.astimezone(UTC))

    @property
    def matches(self) -> bool:
        return self.base.current == self.source.current

    @property
    def publishable(self) -> bool:
        return self.matches

    @property
    def conflict(self) -> bool:
        return not self.matches

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': _SOURCE_VERIFICATION_DOCUMENT_TYPE,
            'schema_version': _SOURCE_VERIFICATION_SCHEMA_VERSION,
            'workspace_revision': self.workspace_revision,
            'base_source_snapshot': _source_snapshot_to_document(self.base),
            'current_source_snapshot': _source_snapshot_to_document(self.source),
            'checked_at_utc': self.checked_at_utc.isoformat(),
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> ManagerSourceVerification:
        try:
            base_document = document['base_source_snapshot']
            source_document = document['current_source_snapshot']
            if (
                document.get('document_type') != _SOURCE_VERIFICATION_DOCUMENT_TYPE
                or document.get('schema_version') != _SOURCE_VERIFICATION_SCHEMA_VERSION
                or not isinstance(base_document, dict)
                or not isinstance(source_document, dict)
            ):
                raise TypeError
            return cls(
                workspace_revision=str(document['workspace_revision']),
                base=_source_snapshot_from_document(base_document),
                source=_source_snapshot_from_document(source_document),
                checked_at_utc=datetime.fromisoformat(str(document['checked_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Manager source verification document is invalid') from error


@dataclass(frozen=True, slots=True)
class ManagerPublicationContext:
    workspace_revision: str
    source_key: SourceKey
    basis_release: SourceReleaseRef | None
    expected_concurrency_token: ConcurrencyToken | None

    def matches_payload(self, payload: dict[str, object]) -> bool:
        return build_workspace_revision(payload) == self.workspace_revision


@dataclass(frozen=True, slots=True)
class ManagerWorkspaceState:
    workspace: ManagerWorkspace | None
    source: SourceReadResult
    verification: ManagerSourceVerification | None
    lifecycle: object


class ManagerWorkspaceController:
    def __init__(self, coordinator: object) -> None:
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
    ) -> ManagerWorkspaceState:
        from atlanticus.web.manager.lifecycle import resolve_manager_lifecycle

        workspace = self.safe_workspace(workspace_document, principal)
        source = self._coordinator.load_current_source(module_key, principal)
        verification = self.safe_verification(verification_document, workspace)
        lifecycle = resolve_manager_lifecycle(
            workspace=workspace,
            editor_revision=_optional_revision(editor_revision),
            source=source,
            validation_current=self.validation_is_current(workspace, validation_document),
            source_verification=verification,
        )
        return ManagerWorkspaceState(workspace, source, verification, lifecycle)

    def require_workspace(
        self,
        document: dict[str, object] | None,
        principal: ManagerPrincipal,
    ) -> ManagerWorkspace:
        if not isinstance(document, dict):
            raise ManagerProjectionError('A browser workspace is required')
        try:
            workspace = ManagerWorkspace.from_document(document)
        except ValueError as error:
            raise ManagerProjectionError('Browser workspace is invalid') from error
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
            raise ManagerProjectionError('A current source verification is required')
        return verification

    def has_local_work(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        editor_revision: object,
    ) -> bool:
        from atlanticus.web.manager.lifecycle import resolve_manager_lifecycle

        workspace = self.safe_workspace(workspace_document, principal)
        local_editor_revision = _optional_revision(editor_revision)
        if workspace is None:
            if workspace_document is not None:
                return False
            return local_editor_revision is not None
        source = self._coordinator.load_current_source(module_key, principal)
        lifecycle = resolve_manager_lifecycle(
            workspace=workspace,
            editor_revision=local_editor_revision,
            source=source,
            validation_current=False,
            source_verification=None,
        )
        return lifecycle.can_discard_local

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
            raise ManagerProjectionError('Validated draft revision does not match browser workspace')
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
        source = self._coordinator.get_source_snapshot(module_key, principal)
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
    ) -> tuple[SourcePublicationResult, dict[str, object]]:
        workspace = self.require_workspace(workspace_document, principal)
        if _optional_revision(editor_revision) != workspace.revision:
            raise ManagerProjectionError('Current editor changes must be saved before publication')
        if not self.validation_is_current(workspace, validation_document):
            raise ManagerProjectionError('A successful draft validation is required')
        verification = self.require_verification(verification_document, workspace)
        if not verification.publishable:
            raise ManagerSourceConflictError('Manager source verification detected a conflict')
        result = self._coordinator.publish_draft(
            module_key,
            principal,
            workspace.payload,
            verification.source,
        )
        if not isinstance(workspace_document, dict):
            raise ManagerProjectionError('A browser workspace is required')
        return result, rebase_workspace_document(workspace_document, result.source.snapshot)

    def refresh_verification(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        try:
            workspace = self.require_workspace(workspace_document, principal)
            source = self._coordinator.get_source_snapshot(module_key, principal)
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
            raise ManagerProjectionError('A browser workspace is required')
        return rebase_workspace_document(workspace_document, verification.source)

    def replace_from_source(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
    ) -> dict[str, object] | None:
        source = self._coordinator.load_current_source(module_key, principal)
        if source.payload is None:
            return None
        workspace = self.safe_workspace(workspace_document, principal)
        owner = workspace.owner_subject_id if workspace is not None else principal.subject_id
        replacement = ManagerWorkspace.create(
            owner_subject_id=owner,
            payload=source.payload,
            base=source.snapshot,
        )
        return replacement.to_document()

    def replace_with_payload(
        self,
        *,
        principal: ManagerPrincipal,
        workspace_document: dict[str, object] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        workspace = self.require_workspace(workspace_document, principal)
        return workspace.with_payload(payload).to_document()

    def create_with_payload_on_current_base(
        self,
        *,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
    ) -> dict[str, object]:
        source = self._coordinator.load_current_source(module_key, principal)
        current_payload = source.payload if source.payload is not None else {}
        current = ManagerWorkspace.create(
            owner_subject_id=principal.subject_id,
            payload=current_payload,
            base=source.snapshot,
        )
        return current.with_payload(payload).to_document()

    @staticmethod
    def source_changed(workspace: ManagerWorkspace, source: SourceReadResult) -> bool:
        return workspace.base.current != source.snapshot.current


def verify_workspace_source(
    workspace: ManagerWorkspace,
    source: SourceSnapshot,
    *,
    checked_at_utc: datetime | None = None,
) -> ManagerSourceVerification:
    return ManagerSourceVerification(
        workspace_revision=workspace.revision,
        base=workspace.base,
        source=source,
        checked_at_utc=(checked_at_utc or datetime.now(UTC)).astimezone(UTC),
    )


def rebase_workspace_document(
    document: dict[str, object],
    source_snapshot: SourceSnapshot,
    *,
    saved_at_utc: datetime | None = None,
) -> dict[str, object]:
    workspace = ManagerWorkspace.from_document(document)
    rebased = workspace.rebase(source_snapshot, saved_at_utc=saved_at_utc)
    updated = deepcopy(document)
    updated.update(rebased.to_document())
    return updated


def prepare_publication(verification: ManagerSourceVerification) -> ManagerPublicationContext:
    if not verification.matches:
        raise ValueError('Manager source changed while the workspace was being edited')
    return _publication_context(verification)


def prepare_conflict_overwrite(
    verification: ManagerSourceVerification,
) -> ManagerPublicationContext:
    if not verification.conflict:
        raise ValueError('Manager conflict overwrite requires a source conflict')
    return _publication_context(verification)


def select_projection_target(source: SourceSnapshot) -> ProjectionTarget:
    if source.current is None:
        raise ValueError('Cannot select a projection target without a published source release')
    return ProjectionTarget(source_key=source.source_key, source_release=source.current.release_ref)


def resolve_manager_projection_state(status: ProjectionStatus) -> ManagerProjectionState:
    if status.source_current_release is None:
        return ManagerProjectionState.NO_SOURCE
    if status.alignment is ProjectionAlignment.NEVER_PROJECTED:
        return ManagerProjectionState.NEVER_PROJECTED
    if status.alignment is ProjectionAlignment.CURRENT:
        return ManagerProjectionState.CURRENT
    if status.alignment is ProjectionAlignment.OUTDATED:
        return ManagerProjectionState.OUTDATED
    raise ValueError('Unsupported projection alignment')


def build_workspace_revision(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _publication_context(
    verification: ManagerSourceVerification,
) -> ManagerPublicationContext:
    basis_release = verification.base.current.release_ref if verification.base.current is not None else None
    return ManagerPublicationContext(
        workspace_revision=verification.workspace_revision,
        source_key=verification.source.source_key,
        basis_release=basis_release,
        expected_concurrency_token=verification.source.concurrency_token,
    )


def _source_snapshot_to_document(snapshot: SourceSnapshot) -> dict[str, object]:
    current = None
    if snapshot.current is not None:
        current = {
            'release_id': snapshot.current.release_ref.release_id.value,
            'published_at_utc': snapshot.current.release_ref.published_at_utc.isoformat(),
            'content_hash': {
                'algorithm': snapshot.current.content_hash.algorithm,
                'value': snapshot.current.content_hash.value,
            },
        }
    return {
        'source_key': snapshot.source_key.value,
        'current': current,
        'concurrency_token': snapshot.concurrency_token.value if snapshot.concurrency_token else None,
    }


def _source_snapshot_from_document(document: dict[str, object]) -> SourceSnapshot:
    current_document = document.get('current')
    current = None
    if current_document is not None:
        if not isinstance(current_document, dict):
            raise TypeError
        content_hash_document = current_document['content_hash']
        if not isinstance(content_hash_document, dict):
            raise TypeError
        current = SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(str(current_document['release_id'])),
                published_at_utc=datetime.fromisoformat(str(current_document['published_at_utc'])),
            ),
            content_hash=Digest(
                algorithm=str(content_hash_document['algorithm']),
                value=str(content_hash_document['value']),
            ),
        )
    token_value = document.get('concurrency_token')
    token = ConcurrencyToken(str(token_value)) if token_value is not None else None
    return SourceSnapshot(
        source_key=SourceKey(str(document['source_key'])),
        current=current,
        concurrency_token=token,
    )


def _optional_revision(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
