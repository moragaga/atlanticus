from datetime import UTC, datetime

from ada.web.kpis.definition.coverage import (
    KpiDefinitionCatalog,
    build_kpi_definition_coverage,
)
from ada.web.kpis.definition.models import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.definition.configuration.projection_record import (
    kpi_definition_projection_from_document,
    kpi_definition_projection_to_document,
)
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def test_projection_record_roundtrip_preserves_exact_registry_dependency() -> None:
    registry = KpiRegistry((KpiRegistryBinding('throughput', ('crusher',)),))
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition('throughput', {'detail': 'Throughput'}),)
    )
    dependency = ProjectionTarget(
        source_key=SourceKey('kpis'),
        source_release=SourceReleaseRef(
            SourceReleaseId('registry-1'),
            datetime(2026, 9, 20, 10, tzinfo=UTC),
        ),
    )
    projection = ProjectionRecord(
        source_key=SourceKey('kpi-definitions'),
        source_release_id=SourceReleaseId('definition-1'),
        source_published_at_utc=datetime(2026, 9, 20, 11, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 20, 11, 1, tzinfo=UTC),
        payload=KpiDefinitionCatalog(
            configuration=configuration,
            coverage=build_kpi_definition_coverage(configuration, registry),
        ),
        dependencies=(dependency,),
    )
    document = kpi_definition_projection_to_document(
        projection,
        item_id='definition',
        partition_key='kpi-definitions',
    )
    restored = kpi_definition_projection_from_document(document)
    assert restored == projection
    assert restored.target == projection.target
