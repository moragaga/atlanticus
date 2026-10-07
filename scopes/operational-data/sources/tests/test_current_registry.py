import pytest

from atlanticus.operational_data.core import DataSource, DataView
from atlanticus.operational_data.sources import (
    DataSourceBindingError,
    PiSourceProvider,
    TimePartitionGranularity,
    build_current_source_registry,
)


def test_current_registry_exposes_all_declared_sources() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    assert set(registry.sources) == set(DataSource)


def test_pi_provider_bindings_are_stable() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    pi = registry.get(DataSource.PI_INTERPOLATED)
    assert pi.definition.key.namespace == ('pi', 'web-api')
    assert pi.get_view(DataView.LATEST).materialization == 'latest'
    assert pi.get_view(DataView.DAILY).time_partition_granularity is TimePartitionGranularity.DAY
    assert pi.get_view(DataView.DAILY).timestamp_column == 'timestamp_utc'
    assert (
        pi.get_view(DataView.MONTHLY).time_partition_granularity is TimePartitionGranularity.MONTH
    )
    recorded = registry.get(DataSource.PI_RECORDED)
    assert set(recorded.views) == {DataView.DAILY, DataView.MONTHLY}
    with pytest.raises(DataSourceBindingError, match='does not support view: latest'):
        registry.get_view(DataSource.PI_RECORDED, DataView.LATEST)


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
    assert dispatch.get_view(DataView.SHIFT).materialization == 'shift'
    assert dispatch.get_view(DataView.SHIFT).shift_column == 'shift_id'
    assert (
        web_api.get(DataSource.REMANENTES_STOCKS).get_view(DataView.LATEST).materialization
        == 'latest'
    )


def test_fabrica_materializations_share_month_partition_contract() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    for source, name in (
        (DataSource.FABRICA_PLANES, 'planes'),
        (DataSource.FABRICA_KPIS, 'kpis'),
    ):
        binding = registry.get(source)
        assert binding.definition.key.namespace == ('fabrica',)
        assert binding.definition.key.name == name
        assert binding.definition.route_segments == ('fabrica', name)
        for view, materialization in (
            (DataView.DAILY, 'daily'),
            (DataView.WEEKLY, 'weekly'),
        ):
            view_binding = binding.get_view(view)
            definition = binding.definition.get_materialization(materialization)
            assert view_binding.materialization == materialization
            assert view_binding.time_partition_granularity is TimePartitionGranularity.MONTH
            assert view_binding.timestamp_column == 'timestamp'
            assert definition.partition_dimensions == ('year', 'month')
            assert definition.resolved_route_segments == (materialization,)


def test_invalid_pi_provider_is_rejected() -> None:
    with pytest.raises(TypeError, match='pi_source must be PiSourceProvider'):
        build_current_source_registry(pi_source='notpii')
