from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ada.configuration.kpi_definition.authority import (
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionCoverageItem,
    KpiDefinitionCoverageStatus,
    build_kpi_definition_coverage,
)
from ada.configuration.kpi_definition.errors import KpiDefinitionProjectionError
from ada.configuration.kpi_definition.models import KpiDefinitionConfiguration

KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE = 'ada_kpi_definition_projection'
KPI_DEFINITION_PROJECTION_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class KpiDefinitionProjection:
    configuration: KpiDefinitionConfiguration
    coverage: tuple[KpiDefinitionCoverageItem, ...]
    revision: str
    source_revision: str
    kpi_configuration_revision: str
    projected_by: str
    projected_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, KpiDefinitionConfiguration):
            raise KpiDefinitionProjectionError('KPI definition projection configuration is invalid')
        coverage = tuple(self.coverage)
        if not all(isinstance(item, KpiDefinitionCoverageItem) for item in coverage):
            raise KpiDefinitionProjectionError('KPI definition projection coverage is invalid')
        source_revision = _required_text(
            self.source_revision,
            'KPI definition projection source revision',
        )
        configuration_revision = _required_text(
            self.kpi_configuration_revision,
            'KPI configuration revision',
        )
        actor = _required_text(
            self.projected_by,
            'KPI definition projection audit actor',
        )
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise KpiDefinitionProjectionError(
                'KPI definition projection timestamp must be timezone-aware'
            )
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected_revision = build_kpi_definition_projection_revision(
            source_revision=source_revision,
            kpi_configuration_revision=configuration_revision,
        )
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise KpiDefinitionProjectionError(
                'KPI definition projection revision does not match dependencies'
            )
        _validate_coverage(self.configuration, coverage)
        object.__setattr__(self, 'coverage', coverage)
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(
            self,
            'kpi_configuration_revision',
            configuration_revision,
        )
        object.__setattr__(self, 'projected_by', actor)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @classmethod
    def create(
        cls,
        *,
        configuration: KpiDefinitionConfiguration,
        source_revision: str,
        authority: KpiDefinitionAuthorityCatalog,
        projected_by: str,
        projected_at_utc: datetime,
    ) -> KpiDefinitionProjection:
        return cls(
            configuration=configuration,
            coverage=build_kpi_definition_coverage(configuration, authority),
            revision=build_kpi_definition_projection_revision(
                source_revision=source_revision,
                kpi_configuration_revision=authority.kpi_configuration_revision,
            ),
            source_revision=source_revision,
            kpi_configuration_revision=authority.kpi_configuration_revision,
            projected_by=projected_by,
            projected_at_utc=projected_at_utc,
        )

    def coverage_item(self, kpi_key: str) -> KpiDefinitionCoverageItem | None:
        normalized = kpi_key.strip() if isinstance(kpi_key, str) else ''
        if not normalized:
            raise KpiDefinitionProjectionError('KPI definition coverage key must not be empty')
        return next(
            (item for item in self.coverage if item.kpi_key == normalized),
            None,
        )

    @property
    def missing_kpi_keys(self) -> tuple[str, ...]:
        return tuple(
            item.kpi_key
            for item in self.coverage
            if item.status is KpiDefinitionCoverageStatus.MISSING
        )

    def to_document(
        self,
        *,
        item_id: str,
        partition_key: str,
    ) -> dict[str, object]:
        normalized_id = _required_text(
            item_id,
            'KPI definition projection item id',
        )
        normalized_partition = _required_text(
            partition_key,
            'KPI definition projection partition key',
        )
        return {
            'id': normalized_id,
            'partition_key': normalized_partition,
            'document_type': KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE,
            'schema_version': KPI_DEFINITION_PROJECTION_SCHEMA_VERSION,
            'revision': self.revision,
            'source_revision': self.source_revision,
            'kpi_configuration_revision': self.kpi_configuration_revision,
            'projected_by': self.projected_by,
            'projected_at_utc': self.projected_at_utc.isoformat(),
            'configuration': self.configuration.to_document(),
            'coverage': [item.to_document() for item in self.coverage],
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> KpiDefinitionProjection:
        if document.get('document_type') != KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE:
            raise KpiDefinitionProjectionError('KPI definition projection document type is invalid')
        if document.get('schema_version') != KPI_DEFINITION_PROJECTION_SCHEMA_VERSION:
            raise KpiDefinitionProjectionError(
                'KPI definition projection schema version is invalid'
            )
        try:
            configuration = document['configuration']
            coverage = document['coverage']
            if not isinstance(configuration, Mapping) or not isinstance(coverage, list):
                raise TypeError
            return cls(
                configuration=KpiDefinitionConfiguration.from_document(configuration),
                coverage=tuple(KpiDefinitionCoverageItem.from_document(item) for item in coverage),
                revision=document['revision'],
                source_revision=document['source_revision'],
                kpi_configuration_revision=document['kpi_configuration_revision'],
                projected_by=document['projected_by'],
                projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, KpiDefinitionProjectionError):
                raise
            raise KpiDefinitionProjectionError(
                'KPI definition projection contract is invalid'
            ) from error


def build_kpi_definition_projection_revision(
    *,
    source_revision: str,
    kpi_configuration_revision: str,
) -> str:
    source = _required_text(
        source_revision,
        'KPI definition projection source revision',
    )
    configuration = _required_text(
        kpi_configuration_revision,
        'KPI configuration revision',
    )
    return hashlib.sha256(f'{source}:{configuration}'.encode('utf-8')).hexdigest()


def _validate_coverage(
    configuration: KpiDefinitionConfiguration,
    coverage: tuple[KpiDefinitionCoverageItem, ...],
) -> None:
    coverage_keys = tuple(item.kpi_key for item in coverage)
    if len(coverage_keys) != len(set(coverage_keys)):
        raise KpiDefinitionProjectionError('KPI definition projection coverage keys must be unique')
    definitions = {definition.kpi_key: definition for definition in configuration.definitions}
    defined_coverage = {
        item.kpi_key: item
        for item in coverage
        if item.status is KpiDefinitionCoverageStatus.DEFINED
    }
    if set(definitions) != set(defined_coverage):
        raise KpiDefinitionProjectionError(
            'KPI definition projection coverage does not match authored definitions'
        )
    for key, definition in definitions.items():
        if dict(defined_coverage[key].fields) != dict(definition.fields):
            raise KpiDefinitionProjectionError(
                'KPI definition projection coverage fields do not match source'
            )


def _required_text(value: object, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ''
    if not normalized:
        raise KpiDefinitionProjectionError(f'{label} must not be empty')
    return normalized
