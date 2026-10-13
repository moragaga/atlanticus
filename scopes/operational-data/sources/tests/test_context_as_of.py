from datetime import UTC, datetime

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
    ShiftScope,
    ShiftSelection,
)
from atlanticus.operational_data.planner import DataInputPlanner
from atlanticus.operational_data.sources import (
    DataInputLoader,
    PiSourceProvider,
    build_current_source_registry,
)


class MissingPartitionReader:
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
        return None


def test_loader_passes_as_of_to_context_even_for_missing_current_shift() -> None:
    as_of = datetime(2026, 8, 21, 0, 2, tzinfo=UTC)
    spec = DataInputSpec(
        input_key='movimiento_mina',
        source=DataSource.DISPATCH_STD_SHIFT_DUMPS,
        view=DataView.SHIFT,
        columns=(DataColumn('tonnage', DataColumnType.FLOAT),),
        selection=ShiftSelection(ShiftScope.CURRENT_TURN),
    )
    plan = DataInputPlanner().plan({'movement': (spec,)})
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    loader = DataInputLoader(reader=MissingPartitionReader(), registry=registry)

    context = loader.load(plan=plan, as_of=as_of).context_for('movement')

    assert context.as_of == as_of
    assert context.get('movimiento_mina').dataframe.empty
