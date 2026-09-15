from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

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
        return _release_id(self.base) == _release_id(self.source)

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
    return ProjectionTarget(
        source_key=source.source_key,
        source_release=source.current.release_ref,
    )


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
    basis_release = None
    if verification.base.current is not None:
        basis_release = verification.base.current.release_ref
    return ManagerPublicationContext(
        workspace_revision=verification.workspace_revision,
        source_key=verification.source.source_key,
        basis_release=basis_release,
        expected_concurrency_token=verification.source.concurrency_token,
    )


def _release_id(snapshot: SourceSnapshot) -> SourceReleaseId | None:
    if snapshot.current is None:
        return None
    return snapshot.current.release_ref.release_id


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
        'concurrency_token': (
            snapshot.concurrency_token.value if snapshot.concurrency_token is not None else None
        ),
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
