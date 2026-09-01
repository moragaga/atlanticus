from __future__ import annotations

# Modela resultados y estado auditables del lifecycle.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ada.configuration.kpi_configuration.errors import KpiConfigurationValidationError

KpiConfigurationIssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class KpiConfigurationAuditRecord:
    actor: str
    occurred_at_utc: datetime

    def __post_init__(self) -> None:
        actor = self.actor.strip() if isinstance(self.actor, str) else ''
        if not actor:
            raise KpiConfigurationValidationError('KPI configuration audit actor must not be empty')
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise KpiConfigurationValidationError(
                'KPI configuration audit timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'actor', actor)
        object.__setattr__(self, 'occurred_at_utc', self.occurred_at_utc.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class KpiConfigurationIssue:
    code: str
    message: str
    level: KpiConfigurationIssueLevel = 'error'
    path: str | None = None

    def __post_init__(self) -> None:
        code = self.code.strip() if isinstance(self.code, str) else ''
        message = self.message.strip() if isinstance(self.message, str) else ''
        if not code or not message:
            raise KpiConfigurationValidationError(
                'KPI configuration issue metadata must not be empty'
            )
        if self.level not in {'error', 'warning'}:
            raise KpiConfigurationValidationError('KPI configuration issue level is invalid')
        path = self.path.strip() if isinstance(self.path, str) else self.path
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'path', path or None)


@dataclass(frozen=True, slots=True)
class KpiConfigurationSummaryItem:
    label: str
    value: str

    def __post_init__(self) -> None:
        label = self.label.strip() if isinstance(self.label, str) else ''
        if not label:
            raise KpiConfigurationValidationError(
                'KPI configuration summary label must not be empty'
            )
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'value', str(self.value))


@dataclass(frozen=True, slots=True)
class KpiConfigurationStatus:
    source_revision: str | None = None
    source_audit: KpiConfigurationAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    active_tool_projection_revision: str | None = None
    projection_audit: KpiConfigurationAuditRecord | None = None

    def __post_init__(self) -> None:
        if (self.source_revision is None) != (self.source_audit is None):
            raise KpiConfigurationValidationError('KPI source status metadata must be complete')
        active = (
            self.active_revision,
            self.active_source_revision,
            self.active_tool_projection_revision,
            self.projection_audit,
        )
        if any(value is not None for value in active) and not all(
            value is not None for value in active
        ):
            raise KpiConfigurationValidationError('KPI projection status metadata must be complete')


@dataclass(frozen=True, slots=True)
class KpiConfigurationValidationResult:
    draft_revision: str
    valid: bool
    audit: KpiConfigurationAuditRecord
    tool_projection_revision: str | None
    issues: tuple[KpiConfigurationIssue, ...] = ()
    summary: tuple[KpiConfigurationSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        revision = self.draft_revision.strip() if isinstance(self.draft_revision, str) else ''
        if not revision:
            raise KpiConfigurationValidationError('KPI draft revision must not be empty')
        object.__setattr__(self, 'draft_revision', revision)
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class KpiConfigurationPublicationResult:
    source_revision: str
    published: bool
    audit: KpiConfigurationAuditRecord
    tool_projection_revision: str
    summary: tuple[KpiConfigurationSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class KpiConfigurationProjectionResult:
    source_revision: str
    projection_revision: str
    tool_projection_revision: str
    projected: bool
    audit: KpiConfigurationAuditRecord
    issues: tuple[KpiConfigurationIssue, ...] = ()
    summary: tuple[KpiConfigurationSummaryItem, ...] = ()
