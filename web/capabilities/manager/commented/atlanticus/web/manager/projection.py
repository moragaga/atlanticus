# Mantiene separados borrador, Source publicado, verificación de Source y Projection activa.
# SourceVerificationResult describe una comprobación puntual sin convertirla en publicación ni proyección.
# Una fuente inexistente es publicable: no existe una revisión remota que proteger mediante compare-and-set.
# Un conflicto real sólo existe cuando hay una revisión remota y difiere de la base conservada por el borrador.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from atlanticus.web.manager.errors import ManagerProjectionError

ProjectionIssueLevel = Literal['error', 'warning']


class ProjectionState(StrEnum):
    NO_SOURCE = 'no_source'
    SYNCHRONIZED = 'synchronized'
    READY = 'ready'
    UNAVAILABLE = 'unavailable'


@dataclass(frozen=True, slots=True)
class ProjectionAuditRecord:
    actor: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ManagerProjectionError('Projection audit actor must not be empty')
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ManagerProjectionError('Projection audit timestamp must be timezone-aware')
        object.__setattr__(self, 'occurred_at', self.occurred_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class ProjectionIssue:
    code: str
    message: str
    level: ProjectionIssueLevel = 'error'
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ManagerProjectionError('Projection issue code must not be empty')
        if not self.message.strip():
            raise ManagerProjectionError('Projection issue message must not be empty')
        if self.level not in {'error', 'warning'}:
            raise ManagerProjectionError('Projection issue level is invalid')


@dataclass(frozen=True, slots=True)
class ProjectionSummaryItem:
    label: str
    value: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ManagerProjectionError('Projection summary label must not be empty')


@dataclass(frozen=True, slots=True)
class ManagerDraft:
    owner_subject_id: str
    revision: str
    saved_at: datetime
    payload: dict[str, object]
    base_source_revision: str | None = None

    def __post_init__(self) -> None:
        owner = self.owner_subject_id.strip()
        if not owner:
            raise ManagerProjectionError('Manager draft owner must not be empty')
        expected = build_draft_revision(self.payload)
        if self.revision.strip() != expected:
            raise ManagerProjectionError('Manager draft revision does not match payload')
        if self.saved_at.tzinfo is None or self.saved_at.utcoffset() is None:
            raise ManagerProjectionError('Manager draft timestamp must be timezone-aware')
        base = self.base_source_revision
        if base is not None:
            base = base.strip() or None
        object.__setattr__(self, 'owner_subject_id', owner)
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'saved_at', self.saved_at.astimezone(UTC))
        object.__setattr__(self, 'base_source_revision', base)
        object.__setattr__(self, 'payload', dict(self.payload))

    @classmethod
    def create(
        cls,
        *,
        owner_subject_id: str,
        payload: dict[str, object],
        base_source_revision: str | None,
        saved_at: datetime | None = None,
    ) -> ManagerDraft:
        return cls(
            owner_subject_id=owner_subject_id,
            revision=build_draft_revision(payload),
            saved_at=(saved_at or datetime.now(UTC)).astimezone(UTC),
            payload=payload,
            base_source_revision=base_source_revision,
        )

    def with_base_source_revision(self, revision: str) -> ManagerDraft:
        return ManagerDraft(
            owner_subject_id=self.owner_subject_id,
            revision=self.revision,
            saved_at=self.saved_at,
            payload=self.payload,
            base_source_revision=revision,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'schema_version': 1,
            'owner_subject_id': self.owner_subject_id,
            'revision': self.revision,
            'saved_at': self.saved_at.isoformat(),
            'base_source_revision': self.base_source_revision,
            'payload': self.payload,
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> ManagerDraft:
        try:
            payload = document['payload']
            if document.get('schema_version') != 1 or not isinstance(payload, dict):
                raise TypeError
            return cls(
                owner_subject_id=str(document['owner_subject_id']),
                revision=str(document['revision']),
                saved_at=datetime.fromisoformat(str(document['saved_at'])),
                payload=dict(payload),
                base_source_revision=_optional_string(document.get('base_source_revision')),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ManagerProjectionError('Manager draft contract is invalid') from error


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    revision: str
    audit: ProjectionAuditRecord
    payload: dict[str, object]

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise ManagerProjectionError('Source snapshot revision must not be empty')
        object.__setattr__(self, 'payload', dict(self.payload))


@dataclass(frozen=True, slots=True)
class ProjectionStatus:
    source_revision: str | None = None
    source_audit: ProjectionAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    projection_audit: ProjectionAuditRecord | None = None

    def __post_init__(self) -> None:
        if (self.source_revision is None) != (self.source_audit is None):
            raise ManagerProjectionError('Projection source metadata must be complete')
        if self.source_revision is not None and not self.source_revision.strip():
            raise ManagerProjectionError('Projection source revision must not be empty')
        active_values = (
            self.active_revision,
            self.active_source_revision,
            self.projection_audit,
        )
        if any(value is not None for value in active_values) and not all(
            value is not None for value in active_values
        ):
            raise ManagerProjectionError('Projection active metadata must be complete')


@dataclass(frozen=True, slots=True)
class DraftValidationResult:
    draft_revision: str
    valid: bool
    audit: ProjectionAuditRecord
    issues: tuple[ProjectionIssue, ...] = ()
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.draft_revision.strip():
            raise ManagerProjectionError('Draft validation revision must not be empty')
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class SourceVerificationResult:
    draft_revision: str
    base_source_revision: str | None
    source_revision: str | None
    source_audit: ProjectionAuditRecord | None
    checked_at: datetime

    def __post_init__(self) -> None:
        draft_revision = self.draft_revision.strip()
        if not draft_revision:
            raise ManagerProjectionError('Source verification draft revision must not be empty')
        base_source_revision = _optional_string(self.base_source_revision)
        source_revision = _optional_string(self.source_revision)
        if (source_revision is None) != (self.source_audit is None):
            raise ManagerProjectionError('Source verification metadata must be complete')
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ManagerProjectionError('Source verification timestamp must be timezone-aware')
        object.__setattr__(self, 'draft_revision', draft_revision)
        object.__setattr__(self, 'base_source_revision', base_source_revision)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'checked_at', self.checked_at.astimezone(UTC))

    @property
    def matches(self) -> bool:
        return self.base_source_revision == self.source_revision

    @property
    def publishable(self) -> bool:
        return self.source_revision is None or self.matches

    @property
    def conflict(self) -> bool:
        return self.source_revision is not None and not self.matches

    def to_document(self) -> dict[str, object]:
        source_audit = None
        if self.source_audit is not None:
            source_audit = {
                'actor': self.source_audit.actor,
                'occurred_at': self.source_audit.occurred_at.isoformat(),
            }
        return {
            'schema_version': 1,
            'draft_revision': self.draft_revision,
            'base_source_revision': self.base_source_revision,
            'source_revision': self.source_revision,
            'source_audit': source_audit,
            'checked_at': self.checked_at.isoformat(),
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> SourceVerificationResult:
        try:
            if document.get('schema_version') != 1:
                raise TypeError
            source_audit_document = document.get('source_audit')
            source_audit = None
            if source_audit_document is not None:
                if not isinstance(source_audit_document, dict):
                    raise TypeError
                source_audit = ProjectionAuditRecord(
                    actor=str(source_audit_document['actor']),
                    occurred_at=datetime.fromisoformat(str(source_audit_document['occurred_at'])),
                )
            return cls(
                draft_revision=str(document['draft_revision']),
                base_source_revision=_optional_string(document.get('base_source_revision')),
                source_revision=_optional_string(document.get('source_revision')),
                source_audit=source_audit,
                checked_at=datetime.fromisoformat(str(document['checked_at'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ManagerProjectionError('Source verification contract is invalid') from error


@dataclass(frozen=True, slots=True)
class SourcePublicationResult:
    source_revision: str
    published: bool
    audit: ProjectionAuditRecord
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_revision.strip():
            raise ManagerProjectionError('Published source revision must not be empty')
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class ProjectionExecutionResult:
    source_revision: str
    projection_revision: str | None
    projected: bool
    audit: ProjectionAuditRecord
    issues: tuple[ProjectionIssue, ...] = ()
    summary: tuple[ProjectionSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class RevisionHistoryEntry:
    revision: str
    saved_by: str
    saved_at: datetime
    active: bool = False
    current: bool = False

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise ManagerProjectionError('Revision history revision must not be empty')
        if not self.saved_by.strip():
            raise ManagerProjectionError('Revision history actor must not be empty')
        if self.saved_at.tzinfo is None or self.saved_at.utcoffset() is None:
            raise ManagerProjectionError('Revision history timestamp must be timezone-aware')
        object.__setattr__(self, 'saved_at', self.saved_at.astimezone(UTC))


@runtime_checkable
class ConfigurationLifecycleWorkflow(Protocol):
    def get_status(self) -> ProjectionStatus: ...

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult: ...

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult: ...

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult: ...


@runtime_checkable
class RevisionHistoryWorkflow(Protocol):
    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]: ...

    def load_revision(self, revision: str) -> dict[str, object]: ...


def resolve_projection_state(status: ProjectionStatus) -> ProjectionState:
    if status.source_revision is None:
        return ProjectionState.NO_SOURCE
    if (
        status.active_revision is not None
        and status.active_source_revision == status.source_revision
    ):
        return ProjectionState.SYNCHRONIZED
    return ProjectionState.READY


def build_draft_revision(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
