from datetime import UTC, datetime

from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from ada.web.kpis.registry.projection.local import (
    LocalKpiRegistryProjectionStore,
    LocalKpiRegistryProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _record() -> ProjectionRecord[KpiRegistry]:
    published_at = datetime(2026, 9, 20, 12, tzinfo=UTC)
    dependency = ProjectionTarget(
        source_key=SourceKey('tools'),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId('tool-1'),
            published_at_utc=datetime(2026, 9, 20, 11, tzinfo=UTC),
        ),
    )
    return ProjectionRecord(
        source_key=SourceKey('kpis'),
        source_release_id=SourceReleaseId('registry-1'),
        source_published_at_utc=published_at,
        projected_at_utc=published_at,
        payload=KpiRegistry(
            (KpiRegistryBinding(kpi_key='throughput', destination_keys=('crusher',)),)
        ),
        dependencies=(dependency,),
    )


def test_local_registry_projection_round_trip_survives_restart(tmp_path) -> None:
    settings = LocalKpiRegistryProjectionStoreSettings(root=tmp_path)
    record = _record()
    first = LocalKpiRegistryProjectionStore(settings)
    assert first.get_active(record.source_key) is None
    first.replace_active(record)
    restarted = LocalKpiRegistryProjectionStore(settings)
    assert restarted.get_active(record.source_key) == record
