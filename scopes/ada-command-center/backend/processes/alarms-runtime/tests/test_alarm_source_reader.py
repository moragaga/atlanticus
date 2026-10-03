from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from ada.contracts.alarms import AlarmIdentity

from ada_command_center.processes.alarms_runtime import (
    AlarmIterationDataError,
    build_alarm_source_adapter,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    ShiftScope,
    ShiftSelection,
    TimeWindow,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataRequirementPlanner
from atlanticus.operational_data.sources import (
    DataSourceApplications,
    PiSourceProvider,
    build_current_source_registry,
)

_AT = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)


class _ScanRuntime:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def scan_dataframe(self, *, definition, targets, projection_schema, filters):
        target = targets[0]
        self.calls.append(
            (
                definition.key.identifier,
                target.materialization,
                tuple(projection_schema.names),
                filters,
            )
        )
        data = self.frames[(definition.key.identifier, target.materialization)]
        if isinstance(data, Exception):
            raise data
        return SimpleNamespace(dataframe=data.loc[:, list(projection_schema.names)])


def _app() -> DataSourceApplications:
    return DataSourceApplications(
        pi='operational-pi',
        dispatch='operational-dispatch',
        blockgrade='operational-blockgrade',
        remanentes='operational-remanentes',
        fabrica_planes='operational-fabrica-planes',
    )


def _req(source, partition, columns, *, window=None, shift=None):
    return DataRequirement(
        source=source,
        partition=partition,
        columns=tuple(DataColumn(name, DataColumnType.FLOAT) for name in columns),
        time_window=window,
        shift=shift,
    )


def test_all_current_source_partitions_are_registered_without_future_sources() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    actual = {
        (source, partition)
        for source in registry.sources
        for partition in registry.get(source).partitions
    }
    expected = {
        DataSource.PI_INTERPOLATED: {
            DataPartition.LATEST,
            DataPartition.DAILY,
            DataPartition.MONTHLY,
        },
        DataSource.PI_RECORDED: {DataPartition.DAILY, DataPartition.MONTHLY},
        DataSource.DISPATCH_TIEMPOS_MLP: {DataPartition.SHIFT},
        DataSource.DISPATCH_STD_SHIFT_LOADS: {DataPartition.SHIFT},
        DataSource.DISPATCH_STD_SHIFT_STATE: {DataPartition.SHIFT},
        DataSource.DISPATCH_STD_TRUCK: {DataPartition.LATEST},
        DataSource.DISPATCH_STD_SHIFT_GRADE: {DataPartition.SHIFT},
        DataSource.DISPATCH_STD_SHIFT_LOADS_2: {DataPartition.SHIFT},
        DataSource.DISPATCH_STD_SHIFT_DUMPS: {DataPartition.SHIFT},
        DataSource.BLOCKGRADE_MMS_BLOCKGRADE_DETAILS_BUCKET: {DataPartition.SHIFT},
        DataSource.REMANENTES_EXTRAIBLES: {DataPartition.LATEST},
        DataSource.REMANENTES_NO_EXTRAIBLES: {DataPartition.LATEST},
        DataSource.REMANENTES_STOCKS: {DataPartition.LATEST},
        DataSource.FABRICA_PLANES: {DataPartition.DAILY, DataPartition.WEEKLY},
        DataSource.METEODATA_DATA: {DataPartition.DAILY},
        DataSource.METEODATA_PROJECTION: {DataPartition.LATEST},
        DataSource.FABRICA_KPIS: {DataPartition.DAILY, DataPartition.WEEKLY},
    }
    assert actual == {
        (source, partition) for source, partitions in expected.items() for partition in partitions
    }


def test_shared_history_consolidates_read_and_delivers_exact_alarm_windows(tmp_path: Path) -> None:
    from atlanticus.operational_data.sources import build_current_source_registry

    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    pi = registry.get(DataSource.PI_INTERPOLATED).definition.key.identifier
    stamp = pd.Timestamp(_AT)
    frame = pd.DataFrame(
        {
            'timestamp_utc': [stamp - pd.Timedelta(hours=3), stamp - pd.Timedelta(hours=1), stamp],
            'temperature': [1.0, 2.0, 3.0],
            'pressure': [10.0, 20.0, 30.0],
        }
    )
    backend = _ScanRuntime({(pi, 'daily'): frame})
    roots = []

    def factory(root):
        roots.append(root)
        return backend

    loader = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=_app(),
        runtime_factory=factory,
    )
    a = AlarmIdentity(family_key='mill', alarm_key='a')
    b = AlarmIdentity(family_key='mill', alarm_key='b')
    plan = DataRequirementPlanner().plan(
        {
            a.canonical_key: (
                _req(
                    DataSource.PI_INTERPOLATED,
                    DataPartition.DAILY,
                    ('temperature',),
                    window=TimeWindow(2, TimeWindowUnit.HOURS),
                ),
            ),
            b.canonical_key: (
                _req(
                    DataSource.PI_INTERPOLATED,
                    DataPartition.DAILY,
                    ('pressure',),
                    window=TimeWindow(4, TimeWindowUnit.HOURS),
                ),
            ),
        }
    )
    data = loader.load(plan=plan, as_of=_AT)
    aframe = data.data_for(a).get(DataSource.PI_INTERPOLATED, DataPartition.DAILY).dataframe
    bframe = data.data_for(b).get(DataSource.PI_INTERPOLATED, DataPartition.DAILY).dataframe
    assert aframe.columns.tolist() == ['temperature']
    assert aframe['temperature'].tolist() == [2.0, 3.0]
    assert bframe.columns.tolist() == ['pressure']
    assert bframe['pressure'].tolist() == [10.0, 20.0, 30.0]
    assert len(backend.calls) == 1
    assert set(backend.calls[0][2]) == {'temperature', 'pressure', 'timestamp_utc'}
    assert len(backend.calls[0][3]) == 2
    assert roots == [tmp_path / 'operational-pi' / 'datasets']


def test_daily_and_monthly_partitions_are_loaded_separately(tmp_path: Path) -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    pi = registry.get(DataSource.PI_INTERPOLATED).definition.key.identifier
    row = {'timestamp_utc': [_AT], 'temperature': [31.0], 'pressure': [35.0]}
    runtime = _ScanRuntime(
        {
            (pi, 'daily'): pd.DataFrame(row),
            (pi, 'monthly'): pd.DataFrame(row),
        }
    )
    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=_app(),
        runtime_factory=lambda root: runtime,
    )
    a = AlarmIdentity(family_key='mill', alarm_key='daily')
    b = AlarmIdentity(family_key='mill', alarm_key='monthly')
    plan = DataRequirementPlanner().plan(
        {
            a.canonical_key: (
                _req(
                    DataSource.PI_INTERPOLATED,
                    DataPartition.DAILY,
                    ('temperature',),
                    window=TimeWindow(2, TimeWindowUnit.HOURS),
                ),
            ),
            b.canonical_key: (
                _req(
                    DataSource.PI_INTERPOLATED,
                    DataPartition.MONTHLY,
                    ('pressure',),
                    window=TimeWindow(1, TimeWindowUnit.MONTHS),
                ),
            ),
        }
    )
    loaded = adapter.load(plan=plan, as_of=_AT)
    assert (
        loaded.data_for(a)
        .get(DataSource.PI_INTERPOLATED, DataPartition.DAILY)
        .last_value_number('temperature')
        == 31.0
    )
    assert (
        loaded.data_for(b)
        .get(DataSource.PI_INTERPOLATED, DataPartition.MONTHLY)
        .last_value_number('pressure')
        == 35.0
    )
    kinds = [record[1] for record in runtime.calls]
    assert kinds.count('daily') == 1
    assert kinds.count('monthly') == 2
    assert all(len(record[3]) == 2 for record in runtime.calls)


def test_requested_partitions_and_sources_have_independent_routes(tmp_path: Path) -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    pi = registry.get(DataSource.PI_INTERPOLATED).definition.key.identifier
    dispatch = registry.get(DataSource.DISPATCH_STD_TRUCK).definition.key.identifier
    fabrica = registry.get(DataSource.FABRICA_PLANES).definition.key.identifier
    runtimes = {
        'operational-pi': _ScanRuntime(
            {(pi, 'latest'): pd.DataFrame({'value': [12.0], 'timestamp_utc': [_AT]})}
        ),
        'operational-dispatch': _ScanRuntime(
            {(dispatch, 'latest'): pd.DataFrame({'value': [22.0]})}
        ),
        'operational-fabrica-planes': _ScanRuntime(
            {(fabrica, 'weekly'): pd.DataFrame({'value': [32.0]})}
        ),
    }
    roots = []

    def factory(root):
        roots.append(root)
        return runtimes[root.parent.name]

    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.PI_WEB_API,
        applications=_app(),
        runtime_factory=factory,
    )
    alarms = [AlarmIdentity(family_key='mill', alarm_key=str(i)) for i in range(3)]
    plan = DataRequirementPlanner().plan(
        {
            alarms[0].canonical_key: (
                _req(DataSource.PI_INTERPOLATED, DataPartition.LATEST, ('value',)),
            ),
            alarms[1].canonical_key: (
                _req(DataSource.DISPATCH_STD_TRUCK, DataPartition.LATEST, ('value',)),
            ),
            alarms[2].canonical_key: (
                _req(DataSource.FABRICA_PLANES, DataPartition.WEEKLY, ('value',)),
            ),
        }
    )
    data = adapter.load(plan=plan, as_of=_AT)
    assert [data.data_for(alarm).sources for alarm in alarms] == [
        (DataSource.PI_INTERPOLATED,),
        (DataSource.DISPATCH_STD_TRUCK,),
        (DataSource.FABRICA_PLANES,),
    ]
    assert {x.parent.name for x in roots} == set(runtimes)
    assert all(len(runtime.calls) == 1 for runtime in runtimes.values())


def test_shift_partition_selects_only_requested_turn(tmp_path: Path) -> None:
    from atlanticus.operational_data.sources import MineShiftResolver

    selection = ShiftSelection(scope=ShiftScope.CURRENT)
    turn = MineShiftResolver().resolve(selection=selection, as_of=_AT)[0]
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    dataset = registry.get(DataSource.DISPATCH_STD_SHIFT_LOADS).definition.key.identifier
    runtime = _ScanRuntime(
        {
            (dataset, 'shift'): pd.DataFrame({'value': [42.0], 'shift_id': [turn.shift_id]}),
        }
    )
    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=_app(),
        runtime_factory=lambda root: runtime,
    )
    alarm = AlarmIdentity(family_key='mill', alarm_key='shift')
    plan = DataRequirementPlanner().plan(
        {
            alarm.canonical_key: (
                _req(
                    DataSource.DISPATCH_STD_SHIFT_LOADS,
                    DataPartition.SHIFT,
                    ('value',),
                    shift=selection,
                ),
            ),
        }
    )
    context = adapter.load(plan=plan, as_of=_AT).data_for(alarm)
    frame = context.get(DataSource.DISPATCH_STD_SHIFT_LOADS, DataPartition.SHIFT)
    assert frame.last_value_number('value') == 42.0
    assert len(runtime.calls) == 1
    assert runtime.calls[0][1] == 'shift'
    assert 'shift_id' in runtime.calls[0][2]


def test_unconfigured_route_affects_only_requested_source(tmp_path: Path) -> None:
    apps = DataSourceApplications(pi='operational-pi')
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    pi = registry.get(DataSource.PI_INTERPOLATED).definition.key.identifier
    runtime = _ScanRuntime(
        {(pi, 'latest'): pd.DataFrame({'value': [10.0], 'timestamp_utc': [_AT]})}
    )
    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=apps,
        runtime_factory=lambda root: runtime,
    )
    a = AlarmIdentity(family_key='mill', alarm_key='a')
    b = AlarmIdentity(family_key='mill', alarm_key='b')
    plan = DataRequirementPlanner().plan(
        {
            a.canonical_key: (_req(DataSource.PI_INTERPOLATED, DataPartition.LATEST, ('value',)),),
            b.canonical_key: (
                _req(DataSource.DISPATCH_STD_TRUCK, DataPartition.LATEST, ('value',)),
            ),
        }
    )
    data = adapter.load(plan=plan, as_of=_AT)
    assert (
        data.data_for(a)
        .get(DataSource.PI_INTERPOLATED, DataPartition.LATEST)
        .last_value_number('value')
        == 10.0
    )
    with pytest.raises(AlarmIterationDataError, match='unavailable') as error:
        data.data_for(b)
    assert error.value.source_key == DataSource.DISPATCH_STD_TRUCK.value
