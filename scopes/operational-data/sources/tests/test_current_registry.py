import pytest

from atlanticus.operational_data.core import DataPartition, DataSource, DataSourceView
from atlanticus.operational_data.sources import (
    DataSourceBindingError,
    PiSourceProvider,
    TimePartitionGranularity,
    build_current_source_registry,
)


def test_current_registry_excludes_unmaterialized_fabrica_kpis() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    assert DataSource.FABRICA_KPIS not in registry.sources
    assert set(registry.sources) == set(DataSource) - {DataSource.FABRICA_KPIS}


def test_pi_provider_bindings_are_stable() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    pi = registry.get(DataSource.PI_INTERPOLATED)
    assert pi.definition.key.namespace == ('pi', 'web-api')
    assert pi.get_partition(DataPartition.LATEST).materialization == 'latest'
    assert pi.get_partition(DataPartition.DAILY).time_partition_granularity is TimePartitionGranularity.DAY
    assert pi.get_partition(DataPartition.DAILY).timestamp_column == 'timestamp_utc'
    assert pi.get_partition(DataPartition.MONTHLY).time_partition_granularity is TimePartitionGranularity.MONTH
    recorded = registry.get(DataSource.PI_RECORDED)
    assert set(recorded.partitions) == {DataPartition.DAILY, DataPartition.MONTHLY}
    with pytest.raises(DataSourceBindingError, match='does not support partition: latest'):
        registry.get_view(DataSourceView(DataSource.PI_RECORDED, DataPartition.LATEST))


def test_non_pi_sources_and_providers_are_stable() -> None:
    web_api = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    notpii = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    assert notpii.get(DataSource.PI_INTERPOLATED).definition.key.namespace == ('pi', 'not_pii')
    assert notpii.get(DataSource.PI_RECORDED).definition.key.namespace == ('pi', 'not_pii')
    for source in web_api.sources:
        if source not in {DataSource.PI_INTERPOLATED, DataSource.PI_RECORDED}:
            assert web_api.get(source) == notpii.get(source)
    dispatch = web_api.get(DataSource.DISPATCH_STD_SHIFT_STATE)
    assert dispatch.definition.key.namespace == ('dispatch',)
    assert dispatch.get_partition(DataPartition.SHIFT).materialization == 'shift'
    assert dispatch.get_partition(DataPartition.SHIFT).shift_column == 'shift_id'
    assert web_api.get(DataSource.REMANENTES_STOCKS).get_partition(DataPartition.LATEST).materialization == 'latest'


def test_fabrica_plans_materialization_is_aligned_with_new_producer_contract() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    plans = registry.get(DataSource.FABRICA_PLANES)
    assert plans.definition.key.namespace == ('fabrica',)
    assert plans.definition.key.name == 'planes'
    assert plans.definition.route_segments == ('fabrica', 'planes')
    assert plans.get_partition(DataPartition.DAILY).materialization == 'daily'
    assert plans.get_partition(DataPartition.WEEKLY).materialization == 'weekly'
    assert plans.definition.get_materialization('daily').resolved_route_segments == ('daily',)
    assert plans.definition.get_materialization('weekly').resolved_route_segments == ('weekly',)


def test_invalid_pi_provider_is_rejected() -> None:
    with pytest.raises(TypeError, match='pi_source must be PiSourceProvider'):
        build_current_source_registry(pi_source='notpii')
