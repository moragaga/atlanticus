from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ada.configuration.kpi_definition.errors import KpiDefinitionProjectionError
from ada.configuration.kpi_definition.models import KpiDefinitionConfiguration

KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE = 'ada_kpi_definition_projection'
KPI_DEFINITION_PROJECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class KpiDefinitionProjection:
    configuration: KpiDefinitionConfiguration
    revision: str
    source_revision: str
    projected_by: str
    projected_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, KpiDefinitionConfiguration):
            raise KpiDefinitionProjectionError('KPI definition projection configuration is invalid')
        source_revision = (
            self.source_revision.strip() if isinstance(self.source_revision, str) else ''
        )
        actor = self.projected_by.strip() if isinstance(self.projected_by, str) else ''
        if not source_revision or not actor:
            raise KpiDefinitionProjectionError(
                'KPI definition projection metadata must not be empty'
            )
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise KpiDefinitionProjectionError(
                'KPI definition projection timestamp must be timezone-aware'
            )
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected_revision = build_kpi_definition_projection_revision(
            source_revision=source_revision,
            projected_by=actor,
            projected_at_utc=occurred_at,
        )
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise KpiDefinitionProjectionError(
                'KPI definition projection revision does not match metadata'
            )
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'projected_by', actor)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @classmethod
    def create(
        cls,
        *,
        configuration: KpiDefinitionConfiguration,
        source_revision: str,
        projected_by: str,
        projected_at_utc: datetime,
    ) -> KpiDefinitionProjection:
        return cls(
            configuration=configuration,
            revision=build_kpi_definition_projection_revision(
                source_revision=source_revision,
                projected_by=projected_by,
                projected_at_utc=projected_at_utc,
            ),
            source_revision=source_revision,
            projected_by=projected_by,
            projected_at_utc=projected_at_utc,
        )

    def to_document(self, *, item_id: str, partition_key: str) -> dict[str, object]:
        normalized_id = item_id.strip() if isinstance(item_id, str) else ''
        normalized_partition_key = partition_key.strip() if isinstance(partition_key, str) else ''
        if not normalized_id or not normalized_partition_key:
            raise KpiDefinitionProjectionError(
                'KPI definition projection identity must not be empty'
            )
        return {
            'id': normalized_id,
            'partition_key': normalized_partition_key,
            'document_type': KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE,
            'schema_version': KPI_DEFINITION_PROJECTION_SCHEMA_VERSION,
            'revision': self.revision,
            'source_revision': self.source_revision,
            'projected_by': self.projected_by,
            'projected_at_utc': self.projected_at_utc.isoformat(),
            'configuration': self.configuration.to_document(),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> KpiDefinitionProjection:
        if document.get('document_type') != KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE:
            raise KpiDefinitionProjectionError('KPI definition projection document type is invalid')
        if document.get('schema_version') != KPI_DEFINITION_PROJECTION_SCHEMA_VERSION:
            raise KpiDefinitionProjectionError(
                'KPI definition projection schema version is invalid'
            )
        try:
            configuration = document['configuration']
            if not isinstance(configuration, dict):
                raise TypeError
            return cls(
                configuration=KpiDefinitionConfiguration.from_document(configuration),
                revision=document['revision'],
                source_revision=document['source_revision'],
                projected_by=document['projected_by'],
                projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise KpiDefinitionProjectionError(
                'KPI definition projection contract is invalid'
            ) from error


def build_kpi_definition_projection_revision(
    *,
    source_revision: str,
    projected_by: str,
    projected_at_utc: datetime,
) -> str:
    normalized_source = source_revision.strip() if isinstance(source_revision, str) else ''
    normalized_actor = projected_by.strip() if isinstance(projected_by, str) else ''
    if not normalized_source or not normalized_actor:
        raise KpiDefinitionProjectionError('KPI definition projection metadata must not be empty')
    if projected_at_utc.tzinfo is None or projected_at_utc.utcoffset() is None:
        raise KpiDefinitionProjectionError(
            'KPI definition projection timestamp must be timezone-aware'
        )
    payload = ':'.join(
        (
            normalized_source,
            normalized_actor,
            projected_at_utc.astimezone(UTC).isoformat(),
        )
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
