from __future__ import annotations

# La proyección conserva el catálogo publicado y expone una NavigationDefinition lista para consumo.


import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from atlanticus.web.navigation.api import NavigationDefinition
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog

IssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class NavigationAuditRecord:
    actor: str
    occurred_at_utc: datetime

    def __post_init__(self) -> None:
        actor = self.actor.strip()
        if not actor:
            raise NavigationConfigurationProjectionError(
                'Navigation audit actor must not be empty'
            )
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise NavigationConfigurationProjectionError(
                'Navigation audit timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'actor', actor)
        object.__setattr__(self, 'occurred_at_utc', self.occurred_at_utc.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class NavigationProjectionIssue:
    code: str
    message: str
    level: IssueLevel = 'error'
    path: str | None = None


@dataclass(frozen=True, slots=True)
class NavigationProjectionSummaryItem:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class NavigationConfigurationProjection:
    revision: str
    source_revision: str
    projected_by: str
    projected_at_utc: datetime
    catalog: NavigationConfigurationCatalog

    def __post_init__(self) -> None:
        source_revision = self.source_revision.strip()
        actor = self.projected_by.strip()
        if not source_revision or not actor:
            raise NavigationConfigurationProjectionError(
                'Navigation projection metadata must not be empty'
            )
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise NavigationConfigurationProjectionError(
                'Navigation projection timestamp must be timezone-aware'
            )
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected = build_navigation_projection_revision(
            source_revision=source_revision,
            projected_at_utc=occurred_at,
        )
        if self.revision.strip() != expected:
            raise NavigationConfigurationProjectionError(
                'Navigation projection revision does not match metadata'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'projected_by', actor)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @property
    def definition(self) -> NavigationDefinition:
        return self.catalog.to_definition()

    @classmethod
    def create(
        cls,
        *,
        source_revision: str,
        projected_by: str,
        catalog: NavigationConfigurationCatalog,
        projected_at_utc: datetime | None = None,
    ) -> NavigationConfigurationProjection:
        occurred_at = (projected_at_utc or datetime.now(UTC)).astimezone(UTC)
        return cls(
            revision=build_navigation_projection_revision(
                source_revision=source_revision,
                projected_at_utc=occurred_at,
            ),
            source_revision=source_revision,
            projected_by=projected_by,
            projected_at_utc=occurred_at,
            catalog=catalog,
        )

    def to_document(
        self,
        *,
        item_id: str | None = None,
        partition_key: str | None = None,
    ) -> dict[str, object]:
        document: dict[str, object] = {
            'document_type': 'atlanticus_navigation_projection',
            'schema_version': 2,
            'revision': self.revision,
            'source_revision': self.source_revision,
            'projected_by': self.projected_by,
            'projected_at_utc': self.projected_at_utc.isoformat(),
            'catalog': self.catalog.to_document(),
        }
        if item_id is not None:
            document['id'] = item_id
        if partition_key is not None:
            document['partition_key'] = partition_key
        return document

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> NavigationConfigurationProjection:
        if document.get('document_type') != 'atlanticus_navigation_projection':
            raise NavigationConfigurationProjectionError(
                'Navigation projection document type is invalid'
            )
        if document.get('schema_version') != 2:
            raise NavigationConfigurationProjectionError(
                'Navigation projection schema version is invalid'
            )
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return cls(
                revision=str(document['revision']),
                source_revision=str(document['source_revision']),
                projected_by=str(document['projected_by']),
                projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
                catalog=NavigationConfigurationCatalog.from_document(dict(catalog)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationProjectionError(
                'Navigation projection contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationProjectionStatus:
    source_revision: str | None = None
    source_audit: NavigationAuditRecord | None = None
    active_revision: str | None = None
    active_source_revision: str | None = None
    projection_audit: NavigationAuditRecord | None = None


@dataclass(frozen=True, slots=True)
class NavigationDraftValidationResult:
    draft_revision: str
    valid: bool
    audit: NavigationAuditRecord
    issues: tuple[NavigationProjectionIssue, ...] = ()
    summary: tuple[NavigationProjectionSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class NavigationSourcePublicationResult:
    source_revision: str
    published: bool
    audit: NavigationAuditRecord
    summary: tuple[NavigationProjectionSummaryItem, ...] = ()


@dataclass(frozen=True, slots=True)
class NavigationProjectionExecutionResult:
    source_revision: str
    projection_revision: str | None
    projected: bool
    audit: NavigationAuditRecord
    issues: tuple[NavigationProjectionIssue, ...] = ()
    summary: tuple[NavigationProjectionSummaryItem, ...] = ()


def build_navigation_projection_revision(
    *,
    source_revision: str,
    projected_at_utc: datetime,
) -> str:
    payload = f'{source_revision.strip()}:{projected_at_utc.astimezone(UTC).isoformat()}'
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
