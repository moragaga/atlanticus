from datetime import UTC, datetime

from atlanticus.operational_data.calendar import MINE_CALENDAR, PLANT_CALENDAR
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    OperationalScope,
    TimeWindow,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataRequirementPlanner
from atlanticus.operational_data.sources import (
    OperationalWindowResolver,
    PiSourceProvider,
    TimePartitionGranularity,
    build_current_source_registry,
)


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
        assert set(binding.partitions) == {DataPartition.DAILY, DataPartition.WEEKLY}
        assert binding.definition.get_materialization('daily').resolved_route_segments == ('daily',)
        assert binding.definition.get_materialization('weekly').resolved_route_segments == (
            'weekly',
        )

    data = registry.get(DataSource.METEODATA_DATA)
    assert data.definition.key.namespace == ('meteodata',)
    assert data.definition.key.name == 'datos'
    assert set(data.partitions) == {DataPartition.DAILY}
    assert data.get_partition(DataPartition.DAILY).timestamp_column == 'timestamp'
    assert (
        data.get_partition(DataPartition.DAILY).time_partition_granularity
        is TimePartitionGranularity.DAY
    )
    assert data.definition.get_materialization('daily').partition_dimensions == (
        'year',
        'month',
        'day',
    )

    projection = registry.get(DataSource.METEODATA_PROJECTION)
    assert projection.definition.key.namespace == ('meteodata',)
    assert projection.definition.key.name == 'proyeccion'
    assert set(projection.partitions) == {DataPartition.LATEST}
    assert projection.get_partition(DataPartition.LATEST).timestamp_column == 'timestamp'


def test_planner_keeps_fabrica_weekly_independent_of_pi_operational_week() -> None:
    requirements = (
        DataRequirement(
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.DAILY,
            columns=(DataColumn('tag', DataColumnType.FLOAT),),
            operational_scope=OperationalScope.CURRENT_OPERATIONAL_WEEK_MINE,
        ),
        DataRequirement(
            source=DataSource.FABRICA_KPIS,
            partition=DataPartition.WEEKLY,
            columns=(DataColumn('plan', DataColumnType.FLOAT),),
        ),
        DataRequirement(
            source=DataSource.METEODATA_DATA,
            partition=DataPartition.DAILY,
            columns=(DataColumn('mp10', DataColumnType.FLOAT),),
            time_window=TimeWindow(1, TimeWindowUnit.DAYS),
        ),
        DataRequirement(
            source=DataSource.METEODATA_PROJECTION,
            partition=DataPartition.LATEST,
            columns=(DataColumn('proyeccion_mp10', DataColumnType.FLOAT),),
        ),
    )
    plan = DataRequirementPlanner().plan({'integration': requirements})
    assert {(view.source, view.partition) for view in plan.views} == {
        (DataSource.PI_INTERPOLATED, DataPartition.DAILY),
        (DataSource.FABRICA_KPIS, DataPartition.WEEKLY),
        (DataSource.METEODATA_DATA, DataPartition.DAILY),
        (DataSource.METEODATA_PROJECTION, DataPartition.LATEST),
    }
