from datetime import UTC, datetime

from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from ada.web.kpis.registry.projection.cosmos import (
    KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE,
    CosmosKpiRegistryProjectionStore,
    CosmosKpiRegistryProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


class _CosmosClient:
    def __init__(self) -> None:
        self.items = {}

    def find_item(self, *, container_name, item_id, partition_key):
        value = self.items.get((container_name, item_id, partition_key))
        return dict(value) if value is not None else None

    def upsert_item(self, *, container_name, item):
        saved = dict(item)
        self.items[(container_name, str(saved['id']), saved['partition_key'])] = saved
        return saved


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


def test_cosmos_registry_projection_round_trips_exact_target() -> None:
    client = _CosmosClient()
    store = CosmosKpiRegistryProjectionStore(
        client=client,
        settings=CosmosKpiRegistryProjectionStoreSettings(
            container_name='ada-kpi-registry-projection'
        ),
    )
    record = _record()
    store.replace_active(record)
    assert store.get_active(record.source_key) == record
    saved = next(iter(client.items.values()))
    assert saved['partition_key'] == 'kpis'
    assert saved['document_type'] == 'ada_kpi_registry_projection_record'


def test_registry_storage_contract_is_standalone_and_partitioned_by_source_key() -> None:
    resource = KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE
    assert resource.logical_id == 'ada.kpis.registry.projection'
    assert resource.owner == 'ada.kpis.registry'
    assert resource.provider == 'cosmos'
    assert resource.default_physical_name == 'ada-kpi-registry-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
