from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
    TimeWindow,
    TimeWindowSelection,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    DataInputLoader,
    FabricaKpis,
    FabricaPlanes,
    PiInterpolated,
    PiSourceProvider,
    build_current_source_registry,
)

_AT = datetime(2026, 10, 14, 17, 12, 30, tzinfo=UTC)
_VALUE = DataColumn('value', DataColumnType.FLOAT)


class Reader:
    def __init__(self, monthly_frames: dict[str, pd.DataFrame]):
        self.monthly_frames = monthly_frames
        self.calls: list[tuple[str, datetime | None, datetime | None]] = []

    def read_frame(
        self,
        *,
        definition,
        target,
        projection_schema,
        timestamp_column=None,
        start_utc=None,
        end_utc=None,
    ):
        self.calls.append((target.identifier, start_utc, end_utc))
        frame = self.monthly_frames.get(target.identifier)
        if frame is None:
            return None
        selected = frame.reindex(columns=projection_schema.names)
        if timestamp_column is not None:
            timestamps = pd.to_datetime(selected[timestamp_column], utc=True)
            selected = selected.loc[
                (timestamps >= pd.Timestamp(start_utc)) & (timestamps <= pd.Timestamp(end_utc))
            ]
        return selected.reset_index(drop=True)


def _monthly_frame(*values: tuple[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {'timestamp': [pd.Timestamp(timestamp) for timestamp, _ in values],
         'value': [value for _, value in values]}
    )


def _run(factory, months: int, *, as_of: datetime = _AT):
    spec = factory(
        input_key='values',
        columns=(_VALUE,),
        period=TimeWindow(months, TimeWindowUnit.MONTHS),
    )
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    binding = registry.get(spec.source)
    view = binding.get_view(spec.view)
    frames = {}
    for year, month, values in (
        (2025, 12, (('2025-12-31T12:00:00Z', 10.0),)),
        (2026, 1, (('2026-01-02T12:00:00Z', 20.0),)),
        (2026, 9, (('2026-09-30T12:00:00Z', 30.0),)),
        (2026, 10, (('2026-10-01T12:00:00Z', 40.0), ('2026-10-14T12:00:00Z', 50.0))),
    ):
        target = binding.definition.resolve_target(
            materialization=view.materialization,
            partition={'year': f'{year:04d}', 'month': f'{month:02d}'},
        )
        frames[target.identifier] = _monthly_frame(*values)
    reader = Reader(frames)
    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=DataInputPlanner().plan({'sample': (spec,)}), as_of=as_of
    )
    return spec, reader, loaded.context_for('sample').get('values').dataframe


@pytest.mark.parametrize('factory', (
    FabricaPlanes.daily,
    FabricaPlanes.weekly,
    FabricaKpis.daily,
    FabricaKpis.weekly,
))
@pytest.mark.parametrize('months,expected_months,expected_values', (
    (1, ('month=10',), [40.0, 50.0]),
    (2, ('month=09', 'month=10'), [30.0, 40.0, 50.0]),
))
def test_fabrica_months_include_current_month_and_preceding_months(
    factory, months, expected_months, expected_values
):
    spec, reader, frame = _run(factory, months)
    assert spec.selection == TimeWindowSelection(TimeWindow(months, TimeWindowUnit.MONTHS))
    assert tuple(call[0].split('/')[-1] for call in reader.calls) == expected_months
    assert frame['value'].tolist() == expected_values
    assert all(call[1].day == 1 and call[1].hour == 0 for call in reader.calls)
    assert all(call[2] == _AT for call in reader.calls)


@pytest.mark.parametrize('factory', (FabricaPlanes.daily, FabricaKpis.weekly))
def test_fabrica_calendar_months_cross_year_boundary(factory):
    at = datetime(2026, 1, 15, 17, tzinfo=UTC)
    _, reader, frame = _run(factory, 2, as_of=at)
    assert tuple(tuple(call[0].split('/')[-2:]) for call in reader.calls) == (
        ('year=2025', 'month=12'),
        ('year=2026', 'month=01'),
    )
    assert frame['value'].tolist() == [10.0, 20.0]


def test_fabrica_shared_view_unions_load_but_slices_each_consumer():
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    inputs = {
        'current': (FabricaPlanes.daily(input_key='value', columns=(_VALUE,),
                      period=TimeWindow(1, TimeWindowUnit.MONTHS)),),
        'two_months': (FabricaPlanes.daily(input_key='value', columns=(_VALUE,),
                         period=TimeWindow(2, TimeWindowUnit.MONTHS)),),
    }
    binding = registry.get(next(iter(inputs.values()))[0].source)
    frames = {}
    for month, value in (('09', 30.0), ('10', 40.0)):
        target = binding.definition.resolve_target(
            materialization='daily', partition={'year': '2026', 'month': month}
        )
        frames[target.identifier] = _monthly_frame((f'2026-{month}-10T12:00:00Z', value))
    reader = Reader(frames)
    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=DataInputPlanner().plan(inputs), as_of=_AT
    )
    assert len(reader.calls) == 2
    assert loaded.context_for('current').get('value').dataframe['value'].tolist() == [40.0]
    assert loaded.context_for('two_months').get('value').dataframe['value'].tolist() == [30.0, 40.0]


def test_pi_daily_still_rejects_calendar_month_windows():
    with pytest.raises(ValueError, match='do not accept month windows'):
        PiInterpolated.daily(input_key='pi', columns=(_VALUE,),
                             period=TimeWindow(1, TimeWindowUnit.MONTHS))


@pytest.mark.parametrize(('source', 'view'), (
    (DataSource.FABRICA_PLANES, DataView.DAILY),
    (DataSource.FABRICA_PLANES, DataView.WEEKLY),
    (DataSource.FABRICA_KPIS, DataView.DAILY),
    (DataSource.FABRICA_KPIS, DataView.WEEKLY),
))
@pytest.mark.parametrize(('months', 'expected_months', 'expected_values'), (
    (1, ('month=10',), [40.0, 50.0]),
    (2, ('month=09', 'month=10'), [30.0, 40.0, 50.0]),
))
def test_direct_data_input_spec_reads_calendar_months(
    source, view, months, expected_months, expected_values
):
    def direct_spec(*, input_key, columns, period):
        return DataInputSpec(
            input_key=input_key,
            source=source,
            view=view,
            selection=TimeWindowSelection(period),
            columns=columns,
        )

    spec, reader, frame = _run(direct_spec, months)
    assert spec.source is source
    assert spec.view is view
    assert spec.selection == TimeWindowSelection(TimeWindow(months, TimeWindowUnit.MONTHS))
    assert tuple(call[0].split('/')[-1] for call in reader.calls) == expected_months
    assert frame['value'].tolist() == expected_values
