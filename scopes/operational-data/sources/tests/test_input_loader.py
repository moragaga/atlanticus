from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa

from atlanticus.datasets.core.models import DatasetDefinition, DatasetTarget
from atlanticus.operational_data.core import DataColumn, DataColumnType, TimeWindow, TimeWindowUnit
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    DataInputLoader,
    FabricaKpis,
    FabricaPlanes,
    PiInterpolated,
    PiSourceProvider,
    build_current_source_registry,
)


class FakeReader:
    def __init__(self, frames: Mapping[str, pd.DataFrame]) -> None:
        self.frames = dict(frames)
        self.calls: list[tuple[str, pa.Schema, datetime | None, datetime | None]] = []

    def read_frame(
        self,
        *,
        definition: DatasetDefinition,
        target: DatasetTarget,
        projection_schema: pa.Schema,
        timestamp_column: str | None = None,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ) -> pd.DataFrame | None:
        self.calls.append((target.identifier, projection_schema, start_utc, end_utc))
        source = self.frames.get(target.identifier)
        if source is None:
            return None
        frame = pd.DataFrame(index=source.index)
        for field in projection_schema:
            frame[field.name] = source[field.name] if field.name in source.columns else None
        if timestamp_column is not None and start_utc is not None and end_utc is not None:
            timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors='coerce')
            frame = frame.loc[
                (timestamps >= pd.Timestamp(start_utc)) & (timestamps <= pd.Timestamp(end_utc))
            ]
        return frame.reset_index(drop=True)


def _float(name: str) -> DataColumn:
    return DataColumn(name, DataColumnType.FLOAT)


def test_same_source_view_loads_once_and_slices_each_input_key() -> None:
    short = PiInterpolated.daily(
        input_key='short',
        columns=(_float('temperature'),),
        period=TimeWindow(1, TimeWindowUnit.HOURS),
    )
    long = PiInterpolated.daily(
        input_key='long',
        columns=(_float('temperature'), _float('pressure')),
        period=TimeWindow(4, TimeWindowUnit.HOURS),
    )
    plan = DataInputPlanner().plan({'consumer': (short, long)})
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    binding = registry.get(short.source)
    target = binding.definition.resolve_target(
        materialization='daily',
        partition={'year': '2026', 'month': '08', 'day': '19'},
    )
    reader = FakeReader(
        {
            target.identifier: pd.DataFrame(
                {
                    'timestamp_utc': [
                        datetime(2026, 8, 19, 8, 30, tzinfo=UTC),
                        datetime(2026, 8, 19, 10, 30, tzinfo=UTC),
                        datetime(2026, 8, 19, 11, 30, tzinfo=UTC),
                    ],
                    'temperature': [1.0, 2.0, 3.0],
                    'pressure': [10.0, 20.0, 30.0],
                }
            )
        }
    )

    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=plan,
        as_of=datetime(2026, 8, 19, 12, tzinfo=UTC),
    )
    context = loaded.context_for('consumer')

    assert len(reader.calls) == 1
    assert context.input_keys == ('short', 'long')
    assert context.get('short').dataframe['temperature'].tolist() == [3.0]
    assert context.get('long').dataframe['temperature'].tolist() == [1.0, 2.0, 3.0]
    assert list(context.get('short').dataframe.columns) == ['temperature']
    assert list(context.get('long').dataframe.columns) == ['temperature', 'pressure']
    assert reader.calls[0][1].names == ['temperature', 'pressure', 'timestamp_utc']


def test_fabrica_daily_reads_month_partition_and_returns_logical_input() -> None:
    plan_input = FabricaKpis.daily(
        input_key='plan',
        columns=(_float('plan_tonelaje'),),
        period=TimeWindow(2, TimeWindowUnit.DAYS),
    )
    plan = DataInputPlanner().plan({'kpi': (plan_input,)})
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    binding = registry.get(plan_input.source)
    target = binding.definition.resolve_target(
        materialization='daily',
        partition={'year': '2026', 'month': '08'},
    )
    reader = FakeReader(
        {
            target.identifier: pd.DataFrame(
                {
                    'timestamp': [
                        datetime(2026, 8, 16, 12, tzinfo=UTC),
                        datetime(2026, 8, 18, 12, tzinfo=UTC),
                        datetime(2026, 8, 19, 10, tzinfo=UTC),
                    ],
                    'plan_tonelaje': [100.0, 200.0, 300.0],
                }
            )
        }
    )

    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=plan,
        as_of=datetime(2026, 8, 19, 12, tzinfo=UTC),
    )
    frame = loaded.context_for('kpi').get('plan')

    assert len(reader.calls) == 1
    assert reader.calls[0][0] == target.identifier
    assert frame.dataframe['plan_tonelaje'].tolist() == [200.0, 300.0]


def test_fabrica_weekly_reads_multiple_month_partitions() -> None:
    plan_input = FabricaPlanes.weekly(
        input_key='plan',
        columns=(_float('plan_tonelaje'),),
        period=TimeWindow(40, TimeWindowUnit.DAYS),
    )
    plan = DataInputPlanner().plan({'kpi': (plan_input,)})
    registry = build_current_source_registry(pi_source=PiSourceProvider.PI_WEB_API)
    binding = registry.get(plan_input.source)
    july = binding.definition.resolve_target(
        materialization='weekly',
        partition={'year': '2026', 'month': '07'},
    )
    august = binding.definition.resolve_target(
        materialization='weekly',
        partition={'year': '2026', 'month': '08'},
    )
    reader = FakeReader(
        {
            july.identifier: pd.DataFrame(
                {
                    'timestamp': [datetime(2026, 7, 20, 12, tzinfo=UTC)],
                    'plan_tonelaje': [100.0],
                }
            ),
            august.identifier: pd.DataFrame(
                {
                    'timestamp': [datetime(2026, 8, 19, 10, tzinfo=UTC)],
                    'plan_tonelaje': [300.0],
                }
            ),
        }
    )

    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=plan,
        as_of=datetime(2026, 8, 19, 12, tzinfo=UTC),
    )
    frame = loaded.context_for('kpi').get('plan')

    assert [call[0] for call in reader.calls] == [july.identifier, august.identifier]
    assert frame.dataframe['plan_tonelaje'].tolist() == [100.0, 300.0]
