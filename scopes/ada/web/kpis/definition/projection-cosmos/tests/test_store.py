from datetime import UTC, datetime

import pytest

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog, build_kpi_definition_coverage
from ada.web.kpis.definition.configuration.errors import KpiDefinitionProjectionError
from ada.web.kpis.definition.models import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.definition.projection.cosmos import (
    KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE,
    CosmosKpiDefinitionProjectionStore,
    CosmosKpiDefinitionProjectionStoreSettings,
)
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


class _CosmosClient:
    def __init__(self) -> None:
        self.items = {}
        self.fail_reads = False
        self.fail_writes = False

    def find_item(self, *, container_name, item_id, partition_key):
        if self.fail_reads:
            raise CosmosError('read failed')
        value = self.items.get((container_name, item_id, partition_key))
        return dict(value) if value is not None else None

    def upsert_item(self, *, container_name, item):
        if self.fail_writes:
            raise CosmosError('write failed')
        saved = dict(item)
        self.items[(container_name, str(saved['id']), saved['partition_key'])] = saved
        return saved


def _record() -> ProjectionRecord[KpiDefinitionCatalog]:
    registry = KpiRegistry((KpiRegistryBinding('throughput', ('crusher',)),))
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition('throughput', {'detail': 'Throughput'}),)
    )
    return ProjectionRecord(
        source_key=SourceKey('kpi-definitions'),
        source_release_id=SourceReleaseId('definition-1'),
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


def test_cosmos_projection_roundtrip_preserves_exact_target() -> None:
    store = CosmosKpiDefinitionProjectionStore(
        client=_CosmosClient(),
        settings=CosmosKpiDefinitionProjectionStoreSettings(
            container_name='ada-kpi-definition-projection'
        ),
    )
    record = _record()
    assert store.replace_active(record) == record
    loaded = store.get_active(record.source_key)
    assert loaded == record
    assert loaded is not None
    assert loaded.target == record.target


def test_cosmos_projection_wraps_connector_failures() -> None:
    client = _CosmosClient()
    store = CosmosKpiDefinitionProjectionStore(
        client=client,
        settings=CosmosKpiDefinitionProjectionStoreSettings(container_name='definition'),
    )
    record = _record()
    client.fail_reads = True
    with pytest.raises(KpiDefinitionProjectionError):
        store.get_active(record.source_key)
    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(KpiDefinitionProjectionError):
        store.replace_active(record)


def test_cosmos_projection_storage_contract_is_definition_owned() -> None:
    resource = KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE
    assert resource.logical_id == 'ada.kpis.definition.projection'
    assert resource.owner == 'ada.kpis.definition'
    assert resource.provider == 'cosmos'
    assert resource.default_physical_name == 'ada-kpi-definition-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
