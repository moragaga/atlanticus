from __future__ import annotations

# Propaga la revisión de KPI Configuration por Validate, Publish, Status y Project.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ada.configuration.kpi_definition.errors import KpiDefinitionValidationError

KpiDefinitionIssueLevel = Literal['error', 'warning']


def _required_text(value: object, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ''
    if not normalized:
        raise KpiDefinitionValidationError(f'{label} must not be empty')
    return normalized


@dataclass(frozen=True, slots=True)
class KpiDefinitionAuditRecord:
    actor: str
    occurred_at_utc: datetime

    def __post_init__(self) -> None:
        actor = _required_text(self.actor, 'KPI definition audit actor')
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise KpiDefinitionValidationError(
                'KPI definition audit timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'actor', actor)
        object.__setattr__(self, 'occurred_at_utc', self.occurred_at_utc.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class KpiDefinitionIssue:
    code: str
    message: str
    level: KpiDefinitionIssueLevel = 'error'
    path: str | None = None

    def __post_init__(self) -> None:
        code = _required_text(self.code, 'KPI definition issue code')
        message = _required_text(self.message, 'KPI definition issue message')
        if self.level not in {'error', 'warning'}:
            raise KpiDefinitionValidationError(
                'KPI definition lifecycle issue level is invalid'
            )
        path = self.path.strip() if isinstance(self.path, str) else self.path
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'path', path or None)


@dataclass(frozen=True, slots=True)
class KpiDefinitionSummaryItem:
    label: str
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'label',
            _required_text(self.label, 'KPI definition lifecycle summary label'),
        )
        object.__setattr__(self, 'value', str(self.value))


@dataclass(frozen=True, slots=True)
class KpiDefinitionStatus:
    source_revision: str | None = None
    source_audit: KpiDefinitionAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    active_kpi_configuration_revision: str | None = None
    projection_audit: KpiDefinitionAuditRecord | None = None

    def __post_init__(self) -> None:
        if (self.source_revision is None) != (self.source_audit is None):
            raise KpiDefinitionValidationError(
                'KPI definition source status metadata must be complete'
            )
        if self.source_revision is not None:
            _required_text(self.source_revision, 'KPI definition source status revision')
        active = (
            self.active_revision,
            self.active_source_revision,
            self.active_kpi_configuration_revision,
            self.projection_audit,
        )
        if any(value is not None for value in active) and not all(
            value is not None for value in active
        ):
            raise KpiDefinitionValidationError(
                'KPI definition projection status metadata must be complete'
            )
        for value, label in (
            (self.active_revision, 'KPI definition active revision'),
            (self.active_source_revision, 'KPI definition active source revision'),
            (
                self.active_kpi_configuration_revision,
                'KPI definition active KPI configuration revision',
            ),
        ):
            if value is not None:
                _required_text(value, label)


@dataclass(frozen=True, slots=True)
class KpiDefinitionValidationResult:
    draft_revision: str
    valid: bool
    audit: KpiDefinitionAuditRecord
    kpi_configuration_revision: str | None
    issues: tuple[KpiDefinitionIssue, ...] = ()
    summary: tuple[KpiDefinitionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'draft_revision',
            _required_text(self.draft_revision, 'KPI definition draft revision'),
        )
        if not isinstance(self.valid, bool):
            raise KpiDefinitionValidationError(
                'KPI definition validation flag must be boolean'
            )
        if self.kpi_configuration_revision is not None:
            object.__setattr__(
                self,
                'kpi_configuration_revision',
                _required_text(
                    self.kpi_configuration_revision,
                    'KPI configuration revision',
                ),
            )
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class KpiDefinitionPublicationResult:
    source_revision: str
    published: bool
    audit: KpiDefinitionAuditRecord
    kpi_configuration_revision: str
    summary: tuple[KpiDefinitionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'source_revision',
            _required_text(self.source_revision, 'KPI definition source revision'),
        )
        if not isinstance(self.published, bool):
            raise KpiDefinitionValidationError(
                'KPI definition publication flag must be boolean'
            )
        object.__setattr__(
            self,
            'kpi_configuration_revision',
            _required_text(
                self.kpi_configuration_revision,
                'KPI configuration revision',
            ),
        )
        object.__setattr__(self, 'summary', tuple(self.summary))


@dataclass(frozen=True, slots=True)
class KpiDefinitionProjectionResult:
    source_revision: str
    projection_revision: str
    kpi_configuration_revision: str
    projected: bool
    audit: KpiDefinitionAuditRecord
    issues: tuple[KpiDefinitionIssue, ...] = ()
    summary: tuple[KpiDefinitionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'source_revision',
            _required_text(self.source_revision, 'KPI definition source revision'),
        )
        object.__setattr__(
            self,
            'projection_revision',
            _required_text(
                self.projection_revision,
                'KPI definition projection revision',
            ),
        )
        object.__setattr__(
            self,
            'kpi_configuration_revision',
            _required_text(
                self.kpi_configuration_revision,
                'KPI configuration revision',
            ),
        )
        if not isinstance(self.projected, bool):
            raise KpiDefinitionValidationError(
                'KPI definition projected flag must be boolean'
            )
        object.__setattr__(self, 'issues', tuple(self.issues))
        object.__setattr__(self, 'summary', tuple(self.summary))
