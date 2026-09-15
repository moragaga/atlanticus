from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus

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


def resolve_projection_state(status: ProjectionStatus) -> ProjectionState:
    if status.source_current_release is None:
        return ProjectionState.NO_SOURCE
    if status.alignment is ProjectionAlignment.CURRENT:
        return ProjectionState.SYNCHRONIZED
    return ProjectionState.READY
