from __future__ import annotations

# Versiona canónicamente la configuración administrativa.
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ada.configuration.kpi_configuration.errors import KpiConfigurationValidationError
from ada.configuration.kpi_configuration.models import KpiConfiguration

KPI_CONFIGURATION_SOURCE_DOCUMENT_TYPE = 'ada_kpi_configuration_source'
KPI_CONFIGURATION_SOURCE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class KpiConfigurationSourceDocument:
    configuration: KpiConfiguration
    revision: str
    saved_by: str
    saved_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, KpiConfiguration):
            raise KpiConfigurationValidationError('KPI source configuration is invalid')
        expected_revision = build_kpi_configuration_digest(self.configuration)
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise KpiConfigurationValidationError(
                'KPI source revision does not match content'
            )
        actor = self.saved_by.strip() if isinstance(self.saved_by, str) else ''
        if not actor:
            raise KpiConfigurationValidationError(
                'KPI source audit actor must not be empty'
            )
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise KpiConfigurationValidationError(
                'KPI source audit timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'saved_by', actor)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        configuration: KpiConfiguration,
        saved_by: str,
        saved_at_utc: datetime | None = None,
    ) -> KpiConfigurationSourceDocument:
        return cls(
            configuration=configuration,
            revision=build_kpi_configuration_digest(configuration),
            saved_by=saved_by,
            saved_at_utc=saved_at_utc if saved_at_utc is not None else datetime.now(UTC),
        )

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': KPI_CONFIGURATION_SOURCE_DOCUMENT_TYPE,
            'schema_version': KPI_CONFIGURATION_SOURCE_SCHEMA_VERSION,
            'revision': self.revision,
            'saved_by': self.saved_by,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'configuration': self.configuration.to_document(),
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> KpiConfigurationSourceDocument:
        if document.get('document_type') != KPI_CONFIGURATION_SOURCE_DOCUMENT_TYPE:
            raise KpiConfigurationValidationError('KPI source document type is invalid')
        if document.get('schema_version') != KPI_CONFIGURATION_SOURCE_SCHEMA_VERSION:
            raise KpiConfigurationValidationError('KPI source schema version is invalid')
        try:
            configuration = document['configuration']
            if not isinstance(configuration, Mapping):
                raise TypeError
            return cls(
                configuration=KpiConfiguration.from_document(configuration),
                revision=document['revision'],
                saved_by=document['saved_by'],
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, KpiConfigurationValidationError):
                raise
            raise KpiConfigurationValidationError('KPI source contract is invalid') from error


def build_kpi_configuration_digest(configuration: KpiConfiguration) -> str:
    if not isinstance(configuration, KpiConfiguration):
        raise KpiConfigurationValidationError('KPI configuration is invalid')
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()
