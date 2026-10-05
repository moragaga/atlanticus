import pytest

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScope,
    OperationalScopeSelection,
    TimeWindow,
    TimeWindowSelection,
    TimeWindowUnit,
)
from atlanticus.operational_data.planner import DataInputPlanner, DataPlanSchemaError


def _float(name: str) -> DataColumn:
    return DataColumn(name, DataColumnType.FLOAT)


def _text(name: str) -> DataColumn:
    return DataColumn(name, DataColumnType.TEXT)


def test_same_consumer_can_request_same_source_view_with_distinct_input_keys() -> None:
    current = DataInputSpec(
        input_key='current',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.DAILY,
        columns=(_float('tonelaje'),),
        selection=OperationalScopeSelection(OperationalScope.CURRENT_TURN_PLANT),
    )
    previous = DataInputSpec(
        input_key='previous',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.DAILY,
        columns=(_float('tonelaje'),),
        selection=OperationalScopeSelection(OperationalScope.PREVIOUS_TURN_PLANT),
    )

    plan = DataInputPlanner().plan({'delta': (current, previous)})

    assert plan.inputs_for('delta') == (current, previous)
    assert len(plan.views) == 1
    view = plan.view_plan(DataSource.PI_INTERPOLATED, DataView.DAILY)
    assert view.column_names == ('tonelaje',)
    assert view.operational_scopes == (
        OperationalScope.CURRENT_TURN_PLANT,
        OperationalScope.PREVIOUS_TURN_PLANT,
    )


def test_planner_merges_columns_and_windows_across_consumers() -> None:
    short = DataInputSpec(
        input_key='short',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.DAILY,
        columns=(_float('temperature'),),
        selection=TimeWindowSelection(TimeWindow(1, TimeWindowUnit.HOURS)),
    )
    long = DataInputSpec(
        input_key='long',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.DAILY,
        columns=(_float('pressure'),),
        selection=TimeWindowSelection(TimeWindow(4, TimeWindowUnit.HOURS)),
    )

    plan = DataInputPlanner().plan({'alarm': (short,), 'kpi': (long,)})

    assert len(plan.views) == 1
    view = plan.views[0]
    assert view.column_names == ('temperature', 'pressure')
    assert tuple(window.value for window in view.time_windows) == (1, 4)


def test_planner_rejects_duplicate_input_keys_inside_one_consumer() -> None:
    first = DataInputSpec(
        input_key='actual',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.LATEST,
        columns=(_float('a'),),
    )
    second = DataInputSpec(
        input_key='actual',
        source=DataSource.REMANENTES_STOCKS,
        view=DataView.LATEST,
        columns=(_float('b'),),
    )

    with pytest.raises(ValueError, match='data input keys must be unique'):
        DataInputPlanner().plan({'consumer': (first, second)})


def test_planner_rejects_conflicting_column_types_in_same_source_view() -> None:
    first = DataInputSpec(
        input_key='a',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.LATEST,
        columns=(_float('shared'),),
    )
    second = DataInputSpec(
        input_key='b',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.LATEST,
        columns=(_text('shared'),),
    )

    with pytest.raises(DataPlanSchemaError, match='float != text'):
        DataInputPlanner().plan({'a': (first,), 'b': (second,)})
