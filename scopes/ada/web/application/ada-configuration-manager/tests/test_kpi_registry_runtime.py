from datetime import UTC, datetime

from ada.web.application.configuration_manager.local_runtime import (
    KPI_REGISTRY_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    create_local_configuration_manager_dependencies,
)
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceReleaseId, SourceReleaseRef


def test_local_runtime_registry_projection_survives_recomposition(tmp_path) -> None:
    source_root = tmp_path / 'source'
    first = create_local_configuration_manager_dependencies(
        source_root=source_root,
    )

    tool_published_at = datetime(2026, 9, 20, 10, tzinfo=UTC)
    registry_published_at = datetime(2026, 9, 20, 11, tzinfo=UTC)

    projection = ProjectionRecord(
        source_key=KPI_REGISTRY_SOURCE_KEY,
        source_release_id=SourceReleaseId('registry-1'),
        source_published_at_utc=registry_published_at,
        projected_at_utc=datetime(2026, 9, 20, 11, 1, tzinfo=UTC),
        payload=KpiRegistry(
            bindings=(
                KpiRegistryBinding(
                    kpi_key='throughput',
                    destination_keys=('global_indicators',),
                ),
            ),
        ),
        dependencies=(
            ProjectionTarget(
                source_key=TOOLS_SOURCE_KEY,
                source_release=SourceReleaseRef(
                    release_id=SourceReleaseId('tools-1'),
                    published_at_utc=tool_published_at,
                ),
            ),
        ),
    )

    first.kpi_registry_projection_store.replace_active(projection)

    restarted = create_local_configuration_manager_dependencies(
        source_root=source_root,
    )
    loaded = restarted.kpi_registry_projection_store.get_active(
        KPI_REGISTRY_SOURCE_KEY
    )

    assert loaded == projection
    assert loaded is not None
    assert loaded.target == projection.target
