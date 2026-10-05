import pytest

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputContext,
    DataInputNotRequestedError,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScope,
    OperationalScopeSelection,
    validate_data_inputs,
)


class _Frame:
    @property
    def dataframe(self):
        return object()

    def last_row(self):
        return object()

    def last_value(self, column, default=None):
        return default

    def last_value_number(self, column, default=None):
        return default


def test_data_input_spec_has_local_identity_and_logical_view() -> None:
    spec = DataInputSpec(
        input_key='actual',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.DAILY,
        columns=(DataColumn('tonelaje', DataColumnType.FLOAT),),
        selection=OperationalScopeSelection(OperationalScope.CURRENT_TURN_PLANT),
    )

    assert spec.input_key == 'actual'
    assert spec.source is DataSource.PI_INTERPOLATED
    assert spec.view is DataView.DAILY
    assert spec.column_names == ('tonelaje',)


def test_data_input_spec_rejects_duplicate_columns() -> None:
    column = DataColumn('tonelaje', DataColumnType.FLOAT)

    with pytest.raises(ValueError, match='column names must be unique'):
        DataInputSpec(
            input_key='actual',
            source=DataSource.PI_INTERPOLATED,
            view=DataView.DAILY,
            columns=(column, column),
        )


def test_data_input_context_resolves_only_declared_input_keys() -> None:
    frame = _Frame()
    context = DataInputContext({'actual': frame, 'plan': frame})

    assert context.input_keys == ('actual', 'plan')
    assert context.get('actual') is frame

    with pytest.raises(DataInputNotRequestedError, match='missing'):
        context.get('missing')


def test_data_input_collection_requires_unique_local_keys() -> None:
    column = DataColumn('tonelaje', DataColumnType.FLOAT)
    first = DataInputSpec(
        input_key='actual',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.LATEST,
        columns=(column,),
    )
    second = DataInputSpec(
        input_key='actual',
        source=DataSource.REMANENTES_STOCKS,
        view=DataView.LATEST,
        columns=(column,),
    )

    with pytest.raises(ValueError, match='input keys must be unique'):
        validate_data_inputs((first, second))
