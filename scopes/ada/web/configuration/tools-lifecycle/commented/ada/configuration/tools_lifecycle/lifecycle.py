from __future__ import annotations

# Resultados tipados del lifecycle que luego puede adaptar el Manager sin acoplar el dominio.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ada.configuration.tools import ToolConfigurationValidationError

ToolLifecycleIssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class ToolLifecycleAuditRecord:
    actor: str
    occurred_at_utc: datetime

    def __post_init__(self) -> None:
        actor = self.actor.strip() if isinstance(self.actor, str) else ''
        if not actor:
            raise ToolConfigurationValidationError('Tool lifecycle audit actor must not be empty')
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise ToolConfigurationValidationError(
                'Tool lifecycle audit timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'actor', actor)
        object.__setattr__(self, 'occurred_at_utc', self.occurred_at_utc.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class ToolLifecycleIssue:
    code: str
    message: str
    level: ToolLifecycleIssueLevel = 'error'
    path: str | None = None

    def __post_init__(self) -> None:
        code = self.code.strip() if isinstance(self.code, str) else ''
        message = self.message.strip() if isinstance(self.message, str) else ''
        if not code or not message:
            raise ToolConfigurationValidationError(
                'Tool lifecycle issue metadata must not be empty'
            )
        if self.level not in {'error', 'warning'}:
            raise ToolConfigurationValidationError('Tool lifecycle issue level is invalid')
        path = self.path.strip() if isinstance(self.path, str) else self.path
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'path', path or None)


@dataclass(frozen=True, slots=True)
class ToolLifecycleSummaryItem:
    label: str
    value: str

    def __post_init__(self) -> None:
        label = self.label.strip() if isinstance(self.label, str) else ''
        if not label:
            raise ToolConfigurationValidationError('Tool lifecycle summary label must not be empty')
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'value', str(self.value))


@dataclass(frozen=True, slots=True)
class ToolLifecycleStatus:
    source_revision: str | None = None
    source_audit: ToolLifecycleAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    projection_audit: ToolLifecycleAuditRecord | None = None

    def __post_init__(self) -> None:
        if (self.source_revision is None) != (self.source_audit is None):
            raise ToolConfigurationValidationError(
                'Tool lifecycle source status metadata must be complete'
            )
        if self.source_revision is not None and not self.source_revision.strip():
            raise ToolConfigurationValidationError(
                'Tool lifecycle source status revision must not be empty'
            )
        active_values = (
            self.active_revision,
            self.active_source_revision,
            self.projection_audit,
        )
        if any(value is not None for value in active_values) and not all(
            value is not None for value in active_values
        ):
            raise ToolConfigurationValidationError(
                'Tool lifecycle projection status metadata must be complete'
            )


@dataclass(frozen=True, slots=True)
class ToolLifecycleValidationResult:
    draft_revision: str
    valid: bool
    audit: ToolLifecycleAuditRecord
    issues: tuple[ToolLifecycleIssue, ...] = ()
    summary: tuple[ToolLifecycleSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        revision = self.draft_revision.strip() if isinstance(self.draft_revision, str) else ''
        if not revision:
            raise ToolConfigurationValidationError(
                'Tool lifecycle draft revision must not be empty'
            )
        object.__setattr__(self, 'draft_revision', revision)
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class ToolLifecyclePublicationResult:
    source_revision: str
    published: bool
    audit: ToolLifecycleAuditRecord
    summary: tuple[ToolLifecycleSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        revision = self.source_revision.strip() if isinstance(self.source_revision, str) else ''
        if not revision:
            raise ToolConfigurationValidationError(
                'Tool lifecycle published source revision must not be empty'
            )
        object.__setattr__(self, 'source_revision', revision)
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class ToolLifecycleProjectionResult:
    source_revision: str
    projection_revision: str
    projected: bool
    audit: ToolLifecycleAuditRecord
    issues: tuple[ToolLifecycleIssue, ...] = ()
    summary: tuple[ToolLifecycleSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        source_revision = (
            self.source_revision.strip() if isinstance(self.source_revision, str) else ''
        )
        projection_revision = (
            self.projection_revision.strip() if isinstance(self.projection_revision, str) else ''
        )
        if not source_revision or not projection_revision:
            raise ToolConfigurationValidationError(
                'Tool lifecycle projection result revisions must not be empty'
            )
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'projection_revision', projection_revision)
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))
