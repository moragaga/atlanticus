from datetime import UTC, datetime

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog, build_kpi_definition_coverage
from ada.web.kpis.definition.models import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.definition.projection.local import (
    LocalKpiDefinitionProjectionStore,
    LocalKpiDefinitionProjectionStoreSettings,
)
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _record(release_id: str = 'definition-1') -> ProjectionRecord[KpiDefinitionCatalog]:
    registry = KpiRegistry((KpiRegistryBinding('throughput', ('crusher',)),))
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition('throughput', {'detail': 'Throughput'}),)
    )
    return ProjectionRecord(
        source_key=SourceKey('kpi-definitions'),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=datetime(2026, 9, 20, 11, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 20, 11, 1, tzinfo=UTC),
        payload=KpiDefinitionCatalog(
            configuration=configuration,
            coverage=build_kpi_definition_coverage(configuration, registry),
        ),
        dependencies=(
            ProjectionTarget(
                source_key=SourceKey('kpis'),
                source_release=SourceReleaseRef(
                    SourceReleaseId('registry-1'),
                    datetime(2026, 9, 20, 10, tzinfo=UTC),
                ),
            ),
        ),
    )


def test_local_projection_survives_store_recomposition(tmp_path) -> None:
    settings = LocalKpiDefinitionProjectionStoreSettings(root=tmp_path)
    record = _record()
    first = LocalKpiDefinitionProjectionStore(settings)
    assert first.replace_active(record) == record
    restarted = LocalKpiDefinitionProjectionStore(settings)
    assert restarted.get_active(record.source_key) == record


def test_local_projection_replaces_same_source_key(tmp_path) -> None:
    store = LocalKpiDefinitionProjectionStore(
        LocalKpiDefinitionProjectionStoreSettings(root=tmp_path)
    )
    first = _record('definition-1')
    second = _record('definition-2')
    store.replace_active(first)
    store.replace_active(second)
    assert store.get_active(first.source_key) == second
    assert len(tuple(tmp_path.glob('kpi_definition_projection_*.json'))) == 1
