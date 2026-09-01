from __future__ import annotations

# La proyección puede derivar un catálogo estrecho sin alterar el documento Delivery schema v1.
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from ada.configuration.kpi_configuration.catalog import KpiCatalog
from ada.configuration.kpi_configuration.errors import KpiConfigurationProjectionError
from ada.configuration.kpi_configuration.models import KpiConfiguration

KPI_CONFIGURATION_PROJECTION_DOCUMENT_TYPE = 'ada_kpi_configuration_projection'
KPI_CONFIGURATION_PROJECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class KpiConfigurationProjection:
    configuration: KpiConfiguration
    revision: str
    source_revision: str
    tool_projection_revision: str
    projected_by: str
    projected_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, KpiConfiguration):
            raise KpiConfigurationProjectionError('KPI projection configuration is invalid')
        source_revision = _required_text(
            self.source_revision,
            'KPI projection source revision',
        )
        tool_revision = _required_text(
            self.tool_projection_revision,
            'KPI projection Tool revision',
        )
        actor = _required_text(self.projected_by, 'KPI projection audit actor')
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise KpiConfigurationProjectionError('KPI projection timestamp must be timezone-aware')
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected_revision = build_kpi_configuration_projection_revision(
            source_revision=source_revision,
            tool_projection_revision=tool_revision,
        )
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise KpiConfigurationProjectionError(
                'KPI projection revision does not match dependencies'
            )
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'tool_projection_revision', tool_revision)
        object.__setattr__(self, 'projected_by', actor)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @classmethod
    def create(
        cls,
        *,
        configuration: KpiConfiguration,
        source_revision: str,
        tool_projection_revision: str,
        projected_by: str,
        projected_at_utc: datetime,
    ) -> KpiConfigurationProjection:
        return cls(
            configuration=configuration,
            revision=build_kpi_configuration_projection_revision(
                source_revision=source_revision,
                tool_projection_revision=tool_projection_revision,
            ),
            source_revision=source_revision,
            tool_projection_revision=tool_projection_revision,
            projected_by=projected_by,
            projected_at_utc=projected_at_utc,
        )

    def catalog(self) -> KpiCatalog:
        return KpiCatalog(
            revision=self.revision,
            kpi_keys=tuple(binding.kpi_key for binding in self.configuration.bindings),
        )

    def to_delivery_document(
        self,
        *,
        item_id: str,
        partition_key: str,
    ) -> dict[str, object]:
        return {
            'id': _required_text(item_id, 'KPI projection item id'),
            'partition_key': _required_text(
                partition_key,
                'KPI projection partition key',
            ),
            'document_type': KPI_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
            'schema_version': KPI_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
            'revision': self.revision,
            'tool_projection_revision': self.tool_projection_revision,
            'configuration': self.configuration.to_delivery_document(),
        }


def build_kpi_configuration_projection_revision(
    *,
    source_revision: str,
    tool_projection_revision: str,
) -> str:
    source = _required_text(source_revision, 'KPI projection source revision')
    tool = _required_text(tool_projection_revision, 'KPI projection Tool revision')
    return hashlib.sha256(f'{source}:{tool}'.encode('utf-8')).hexdigest()


def _required_text(value: object, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ''
    if not normalized:
        raise KpiConfigurationProjectionError(f'{label} must not be empty')
    return normalized
