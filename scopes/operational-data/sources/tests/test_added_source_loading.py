from datetime import UTC, datetime

import pandas as pd

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
    TimeWindow,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    DataInputLoader,
    FabricaKpis,
    MeteodataData,
    PiSourceProvider,
    build_current_source_registry,
)


class FakeReader:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

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
        original = self.frames.get(target.identifier)
        if original is None:
            return None
        frame = original.reindex(columns=projection_schema.names)
        if timestamp_column is not None and start_utc is not None:
            timestamps = pd.to_datetime(frame[timestamp_column], utc=True)
            frame = frame.loc[
                (timestamps >= pd.Timestamp(start_utc)) & (timestamps <= pd.Timestamp(end_utc))
            ]
        return frame.reset_index(drop=True)


def _float(name: str) -> DataColumn:
    return DataColumn(name, DataColumnType.FLOAT)


def test_input_loader_consumes_fabrica_and_meteodata_as_distinct_sources() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    as_of = datetime(2026, 8, 20, 12, tzinfo=UTC)
    inputs = (
        DataInputSpec(
            input_key='plans',
            source=DataSource.FABRICA_PLANES,
            view=DataView.DAILY,
            columns=(_float('toneladas'),),
        ),
        FabricaKpis.weekly(
            input_key='kpis',
            columns=(_float('produccion'),),
        ),
        MeteodataData.daily(
            input_key='measurements',
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

    frames = {}
    values = {'plans': 100.0, 'kpis': 200.0, 'measurements': 30.0, 'projection': 40.0}
    for input_spec in inputs:
        binding = registry.get(input_spec.source)
        view_binding = binding.get_view(input_spec.view)
        target_kwargs = {}
        if input_spec.input_key == 'measurements':
            target_kwargs['partition'] = {'year': '2026', 'month': '08', 'day': '20'}
        target = binding.definition.resolve_target(
            materialization=view_binding.materialization,
            **target_kwargs,
        )
        column = input_spec.column_names[0]
        payload = {column: [values[input_spec.input_key]]}
        if input_spec.input_key in {'measurements', 'projection'}:
            payload['timestamp'] = [datetime(2026, 8, 20, 11, tzinfo=UTC)]
        frames[target.identifier] = pd.DataFrame(payload)

    reader = FakeReader(frames)
    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=DataInputPlanner().plan({'integration': inputs}),
        as_of=as_of,
    )
    context = loaded.context_for('integration')

    for input_spec in inputs:
        column = input_spec.column_names[0]
        assert (
            context.get(input_spec.input_key).last_value_number(column)
            == values[input_spec.input_key]
        )
    meteodata_calls = [call for call in reader.calls if call[0].startswith('datasets/meteodata/')]
    assert any(start is not None and end == as_of for _, start, end in meteodata_calls)
