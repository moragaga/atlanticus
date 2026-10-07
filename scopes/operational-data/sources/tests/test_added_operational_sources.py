from datetime import UTC, datetime

from atlanticus.operational_data.calendar import MINE_CALENDAR, PLANT_CALENDAR
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScope,
    TimeWindow,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    FabricaKpis,
    MeteodataData,
    OperationalWindowResolver,
    PiInterpolated,
    PiSourceProvider,
    TimePartitionGranularity,
    build_current_source_registry,
)


def _float(name: str) -> DataColumn:
    return DataColumn(name, DataColumnType.FLOAT)


def test_pi_current_week_uses_existing_area_calendars_and_caps_to_pi_as_of() -> None:
    as_of = datetime(2026, 9, 8, 12, tzinfo=UTC)
    resolver = OperationalWindowResolver()
    for scope, calendar in (
        (OperationalScope.CURRENT_OPERATIONAL_WEEK_MINE, MINE_CALENDAR),
        (OperationalScope.CURRENT_OPERATIONAL_WEEK_PLANT, PLANT_CALENDAR),
    ):
        resolved = resolver.resolve(scope=scope, as_of=as_of)
        week = calendar.resolve_operational_week(as_of)
        assert resolved.start_utc == week.start_utc
        assert resolved.end_utc == as_of


def test_fabrica_and_meteodata_bindings_follow_producer_layouts() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    for source, name in (
        (DataSource.FABRICA_PLANES, 'planes'),
        (DataSource.FABRICA_KPIS, 'kpis'),
    ):
        binding = registry.get(source)
        assert binding.definition.key.namespace == ('fabrica',)
        assert binding.definition.key.name == name
        assert binding.definition.route_segments == ('fabrica', name)
        assert set(binding.views) == {DataView.DAILY, DataView.WEEKLY}
        for view, materialization_name in (
            (DataView.DAILY, 'daily'),
            (DataView.WEEKLY, 'weekly'),
        ):
            view_binding = binding.get_view(view)
            materialization = binding.definition.get_materialization(materialization_name)
            assert materialization.resolved_route_segments == (materialization_name,)
            assert materialization.partition_dimensions == ('year', 'month')
            assert view_binding.time_partition_granularity is TimePartitionGranularity.MONTH
            assert view_binding.timestamp_column == 'timestamp'

    data = registry.get(DataSource.METEODATA_DATA)
    assert data.definition.key.namespace == ('meteodata',)
    assert data.definition.key.name == 'datos'
    assert set(data.views) == {DataView.DAILY}
    assert data.get_view(DataView.DAILY).timestamp_column == 'timestamp'
    assert data.get_view(DataView.DAILY).time_partition_granularity is TimePartitionGranularity.DAY
    assert data.definition.get_materialization('daily').partition_dimensions == (
        'year',
        'month',
        'day',
    )

    projection = registry.get(DataSource.METEODATA_PROJECTION)
    assert projection.definition.key.namespace == ('meteodata',)
    assert projection.definition.key.name == 'proyeccion'
    assert set(projection.views) == {DataView.LATEST}
    assert projection.get_view(DataView.LATEST).timestamp_column == 'timestamp'


def test_planner_keeps_logical_views_independent_across_sources() -> None:
    inputs = (
        PiInterpolated.daily(
            input_key='pi-week',
            columns=(_float('tag'),),
            period=OperationalScope.CURRENT_OPERATIONAL_WEEK_MINE,
        ),
        FabricaKpis.weekly(
            input_key='fabrica-week',
            columns=(_float('plan'),),
            period=OperationalScope.CURRENT_OPERATIONAL_WEEK_PLANT,
        ),
        MeteodataData.daily(
            input_key='weather',
            columns=(_float('mp10'),),
            period=TimeWindow(1, TimeWindowUnit.DAYS),
        ),
        DataInputSpec(
            input_key='projection',
            source=DataSource.METEODATA_PROJECTION,
            view=DataView.LATEST,
            columns=(_float('proyeccion_mp10'),),
        ),
    )
    plan = DataInputPlanner().plan({'integration': inputs})
    assert {(view.source, view.view) for view in plan.views} == {
        (DataSource.PI_INTERPOLATED, DataView.DAILY),
        (DataSource.FABRICA_KPIS, DataView.WEEKLY),
        (DataSource.METEODATA_DATA, DataView.DAILY),
        (DataSource.METEODATA_PROJECTION, DataView.LATEST),
    }
