from datetime import UTC, datetime

import pandas as pd

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    TimeWindow,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataRequirementPlanner
from atlanticus.operational_data.sources import (
    DataSourceLoader,
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


def test_existing_loader_consumes_fabrica_and_meteodata_as_distinct_sources() -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    as_of = datetime(2026, 8, 20, 12, tzinfo=UTC)
    definitions = {
        'plans': (DataSource.FABRICA_PLANES, DataPartition.DAILY, 'toneladas'),
        'kpis': (DataSource.FABRICA_KPIS, DataPartition.WEEKLY, 'produccion'),
        'measurements': (DataSource.METEODATA_DATA, DataPartition.DAILY, 'mp10'),
        'projection': (DataSource.METEODATA_PROJECTION, DataPartition.LATEST, 'proyeccion_mp10'),
    }
    requests = {}
    for key, (source, partition, column) in definitions.items():
        options = {}
        if key == 'measurements':
            options['time_window'] = TimeWindow(1, TimeWindowUnit.DAYS)
        requests[key] = (
            DataRequirement(
                source=source,
                partition=partition,
                columns=(DataColumn(column, DataColumnType.FLOAT),),
                **options,
            ),
        )

    frames = {}
    values = {'plans': 100.0, 'kpis': 200.0, 'measurements': 30.0, 'projection': 40.0}
    for key, (source, partition, column) in definitions.items():
        binding = registry.get(source)
        target_kwargs = {}
        if key == 'measurements':
            target_kwargs['partition'] = {'year': '2026', 'month': '08', 'day': '20'}
        target = binding.definition.resolve_target(materialization=partition.value, **target_kwargs)
        payload = {column: [values[key]]}
        if key in {'measurements', 'projection'}:
            payload['timestamp'] = [datetime(2026, 8, 20, 11, tzinfo=UTC)]
        frames[target.identifier] = pd.DataFrame(payload)

    reader = FakeReader(frames)
    loader = DataSourceLoader(reader=reader, registry=registry)
    loaded = loader.load(plan=DataRequirementPlanner().plan(requests), as_of=as_of)

    for key, (source, partition, column) in definitions.items():
        context = loaded.context_for(key).get(source, partition)
        assert context.last_value_number(column) == values[key]
    meteodata_calls = [call for call in reader.calls if call[0].startswith('datasets/meteodata/')]
    assert any(start is not None and end == as_of for _, start, end in meteodata_calls)
