import pytest

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataSource,
    DataView,
    OperationalScope,
    OperationalScopeSelection,
    ShiftScope,
    ShiftSelection,
    TimeWindow,
    TimeWindowSelection,
    TimeWindowUnit,
)
from atlanticus.operational_data.sources import (
    DispatchShiftLoads,
    FabricaKpis,
    FabricaPlanes,
    MeteodataData,
    PiInterpolated,
    PiRecorded,
    RemanentesStocks,
)


def _float(name='value'):
    return DataColumn(name, DataColumnType.FLOAT)


def test_pi_interpolated_exposes_latest_and_typed_temporal_views() -> None:
    latest = PiInterpolated.latest(input_key='actual', columns=(_float('actual'),))
    daily = PiInterpolated.daily(
        input_key='turn',
        columns=(_float('tonelaje'),),
        period=OperationalScope.CURRENT_TURN_PLANT,
    )
    monthly = PiInterpolated.monthly(
        input_key='month',
        columns=(_float('tonelaje'),),
        period=TimeWindow(2, TimeWindowUnit.MONTHS),
    )

    assert (latest.source, latest.view, latest.selection) == (
        DataSource.PI_INTERPOLATED,
        DataView.LATEST,
        None,
    )
    assert daily.view is DataView.DAILY
    assert daily.selection == OperationalScopeSelection(OperationalScope.CURRENT_TURN_PLANT)
    assert monthly.view is DataView.MONTHLY
    assert monthly.selection == TimeWindowSelection(TimeWindow(2, TimeWindowUnit.MONTHS))


def test_same_source_view_can_define_distinct_local_inputs() -> None:
    current = PiInterpolated.daily(
        input_key='current',
        columns=(_float('tonelaje'),),
        period=OperationalScope.CURRENT_TURN_PLANT,
    )
    previous = PiInterpolated.daily(
        input_key='previous',
        columns=(_float('tonelaje'),),
        period=OperationalScope.PREVIOUS_TURN_PLANT,
    )

    assert current.source == previous.source
    assert current.view == previous.view == DataView.DAILY
    assert current.input_key != previous.input_key
    assert current.selection != previous.selection


def test_source_builders_reject_invalid_temporal_combinations() -> None:
    with pytest.raises(ValueError, match='do not accept month windows'):
        PiRecorded.daily(
            input_key='invalid',
            columns=(_float(),),
            period=TimeWindow(1, TimeWindowUnit.MONTHS),
        )

    with pytest.raises(ValueError, match='require month windows'):
        PiInterpolated.monthly(
            input_key='invalid',
            columns=(_float(),),
            period=TimeWindow(24, TimeWindowUnit.HOURS),
        )


def test_fabrica_daily_and_weekly_inputs_are_temporal() -> None:
    period = TimeWindow(14, TimeWindowUnit.DAYS)
    inputs = (
        FabricaPlanes.daily(
            input_key='planes-daily',
            columns=(_float('planes_daily'),),
            period=period,
        ),
        FabricaPlanes.weekly(
            input_key='planes-weekly',
            columns=(_float('planes_weekly'),),
            period=period,
        ),
        FabricaKpis.daily(
            input_key='kpis-daily',
            columns=(_float('kpis_daily'),),
            period=period,
        ),
        FabricaKpis.weekly(
            input_key='kpis-weekly',
            columns=(_float('kpis_weekly'),),
            period=period,
        ),
    )

    assert [(item.source, item.view) for item in inputs] == [
        (DataSource.FABRICA_PLANES, DataView.DAILY),
        (DataSource.FABRICA_PLANES, DataView.WEEKLY),
        (DataSource.FABRICA_KPIS, DataView.DAILY),
        (DataSource.FABRICA_KPIS, DataView.WEEKLY),
    ]
    assert all(item.selection == TimeWindowSelection(period) for item in inputs)


def test_representative_sources_build_only_their_logical_input_shapes() -> None:
    fabrica = FabricaKpis.daily(
        input_key='plan',
        columns=(_float('plan'),),
        period=OperationalScope.CURRENT_OPERATIONAL_DAY_PLANT,
    )
    dispatch = DispatchShiftLoads.shift(
        input_key='loads',
        columns=(_float('loads'),),
        selection=ShiftSelection(ShiftScope.CURRENT_TURN),
    )
    remanentes = RemanentesStocks.latest(
        input_key='stocks',
        columns=(_float('stocks'),),
    )
    weather = MeteodataData.daily(
        input_key='rain',
        columns=(_float('rain'),),
        period=TimeWindow(12, TimeWindowUnit.HOURS),
    )

    assert (fabrica.source, fabrica.view) == (DataSource.FABRICA_KPIS, DataView.DAILY)
    assert (dispatch.source, dispatch.view) == (
        DataSource.DISPATCH_STD_SHIFT_LOADS,
        DataView.SHIFT,
    )
    assert (remanentes.source, remanentes.view, remanentes.selection) == (
        DataSource.REMANENTES_STOCKS,
        DataView.LATEST,
        None,
    )
    assert (weather.source, weather.view) == (DataSource.METEODATA_DATA, DataView.DAILY)
