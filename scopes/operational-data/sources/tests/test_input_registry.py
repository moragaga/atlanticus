from atlanticus.operational_data.core import DataPartition, DataSource, DataView
from atlanticus.operational_data.sources import (
    PiSourceProvider,
    TimePartitionGranularity,
    build_current_source_registry,
)


def test_registry_resolves_new_data_view_contract() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)

    binding, daily = registry.get_input_view(DataSource.PI_INTERPOLATED, DataView.DAILY)

    assert binding.source is DataSource.PI_INTERPOLATED
    assert daily.partition is DataPartition.DAILY
    assert daily.timestamp_column == 'timestamp_utc'


def test_fabrica_kpis_daily_binding_matches_monthly_physical_materialization() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    kpis = registry.get(DataSource.FABRICA_KPIS)
    daily = kpis.get_partition(DataPartition.DAILY)
    materialization = kpis.definition.get_materialization('daily')

    assert materialization.partition_dimensions == ('year', 'month')
    assert daily.time_partition_granularity is TimePartitionGranularity.MONTH
    assert daily.timestamp_column == 'timestamp'
