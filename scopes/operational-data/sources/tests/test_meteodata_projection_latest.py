from datetime import UTC, datetime

import pandas as pd
import pytest

from atlanticus.operational_data.core import DataColumn, DataColumnType, DataSource, DataView
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    DataInputLoader,
    MeteodataProjection,
    PiSourceProvider,
    build_current_source_registry,
)


class ProjectionReader:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
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
        self.calls.append((definition.key.identifier, target.identifier, start_utc, end_utc))
        return self.frame.reindex(columns=projection_schema.names).reset_index(drop=True)


def test_meteodata_projection_latest_preserves_its_typed_contract() -> None:
    columns = (
        DataColumn('proyeccion_mp10', DataColumnType.FLOAT),
        DataColumn('promedio_dia_mp10', DataColumnType.FLOAT),
        DataColumn('monitoreo_oficial', DataColumnType.BOOLEAN),
    )

    spec = MeteodataProjection.latest(input_key='projection', columns=columns)

    assert (spec.input_key, spec.source, spec.view, spec.selection) == (
        'projection',
        DataSource.METEODATA_PROJECTION,
        DataView.LATEST,
        None,
    )
    assert spec.columns == columns


def test_meteodata_projection_latest_rejects_empty_columns() -> None:
    with pytest.raises(ValueError, match='at least one column'):
        MeteodataProjection.latest(input_key='projection', columns=())


def test_meteodata_projection_latest_loads_producer_fields_without_time_selection() -> None:
    as_of = datetime(2026, 10, 13, 12, tzinfo=UTC)
    spec = MeteodataProjection.latest(
        input_key='projection',
        columns=(
            DataColumn('proyeccion_mp10', DataColumnType.FLOAT),
            DataColumn('promedio_dia_mp10', DataColumnType.FLOAT),
            DataColumn('monitoreo_oficial', DataColumnType.BOOLEAN),
        ),
    )
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    binding, view = registry.get_view(spec.source, spec.view)
    target = binding.definition.resolve_target(materialization=view.materialization)
    reader = ProjectionReader(
        pd.DataFrame(
            {
                'timestamp': [datetime(2026, 10, 13, 11, tzinfo=UTC)],
                'proyeccion_mp10': [42.0],
                'promedio_dia_mp10': [35.5],
                'monitoreo_oficial': [True],
            }
        )
    )

    loaded = DataInputLoader(reader=reader, registry=registry).load(
        plan=DataInputPlanner().plan({'alarm': (spec,)}),
        as_of=as_of,
    )
    context = loaded.context_for('alarm').get('projection')

    assert context.last_value_number('proyeccion_mp10') == 42.0
    assert context.last_value_number('promedio_dia_mp10') == 35.5
    assert bool(context.last_value('monitoreo_oficial')) is True
    assert reader.calls == [(binding.definition.key.identifier, target.identifier, None, None)]
