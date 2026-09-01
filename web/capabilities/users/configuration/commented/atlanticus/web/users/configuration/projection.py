from __future__ import annotations

# Espejo pedagógico: Implementa el dominio administrativo genérico de Users: draft validable, Source versionado, proyección y adapters.

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError

IssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class UsersAuditRecord:
    actor: str
    occurred_at_utc: datetime

    def __post_init__(self) -> None:
        actor = self.actor.strip()
        if not actor:
            raise UsersConfigurationProjectionError('Users audit actor must not be empty')
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise UsersConfigurationProjectionError('Users audit timestamp must be timezone-aware')
        object.__setattr__(self, 'actor', actor)
        object.__setattr__(self, 'occurred_at_utc', self.occurred_at_utc.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class UsersProjectionIssue:
    code: str
    message: str
    level: IssueLevel = 'error'
    path: str | None = None


@dataclass(frozen=True, slots=True)
class UsersProjectionSummaryItem:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class UsersProjectionState:
    revision: str
    source_revision: str
    projected_by: str
    projected_at_utc: datetime

    def __post_init__(self) -> None:
        source_revision = self.source_revision.strip()
        projected_by = self.projected_by.strip()
        if not source_revision or not projected_by:
            raise UsersConfigurationProjectionError('Users projection metadata must not be empty')
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise UsersConfigurationProjectionError(
                'Users projection timestamp must be timezone-aware'
            )
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected = build_users_projection_revision(source_revision, occurred_at)
        if self.revision.strip() != expected:
            raise UsersConfigurationProjectionError(
                'Users projection revision does not match metadata'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'projected_by', projected_by)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @classmethod
    def create(
        cls,
        *,
        source_revision: str,
        projected_by: str,
        projected_at_utc: datetime | None = None,
    ) -> UsersProjectionState:
        occurred_at = (projected_at_utc or datetime.now(UTC)).astimezone(UTC)
        return cls(
            revision=build_users_projection_revision(source_revision, occurred_at),
            source_revision=source_revision,
            projected_by=projected_by,
            projected_at_utc=occurred_at,
        )


@dataclass(frozen=True, slots=True)
class UsersProjectionStatus:
    source_revision: str | None = None
    source_audit: UsersAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    projection_audit: UsersAuditRecord | None = None


@dataclass(frozen=True, slots=True)
class UsersDraftValidationResult:
    draft_revision: str
    valid: bool
    audit: UsersAuditRecord
    issues: tuple[UsersProjectionIssue, ...] = ()
    summary: tuple[UsersProjectionSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class UsersSourcePublicationResult:
    source_revision: str
    published: bool
    audit: UsersAuditRecord
    summary: tuple[UsersProjectionSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class UsersProjectionExecutionResult:
    source_revision: str
    projection_revision: str | None
    projected: bool
    audit: UsersAuditRecord
    issues: tuple[UsersProjectionIssue, ...] = ()
    summary: tuple[UsersProjectionSummaryItem, ...] = ()


def build_users_projection_revision(source_revision: str, projected_at_utc: datetime) -> str:
    payload = f'{source_revision.strip()}:{projected_at_utc.astimezone(UTC).isoformat()}'
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
