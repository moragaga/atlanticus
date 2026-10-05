from __future__ import annotations

from atlanticus.operational_data.core import (
    DataColumn,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScope,
    OperationalScopeSelection,
    ShiftSelection,
    TimeWindow,
    TimeWindowSelection,
    TimeWindowUnit,
)

_DAILY_OPERATIONAL_SCOPES = frozenset(
    {
        OperationalScope.CURRENT_TURN_MINE,
        OperationalScope.PREVIOUS_TURN_MINE,
        OperationalScope.CURRENT_TURN_PLANT,
        OperationalScope.PREVIOUS_TURN_PLANT,
        OperationalScope.CURRENT_OPERATIONAL_DAY_MINE,
        OperationalScope.CURRENT_OPERATIONAL_DAY_PLANT,
        OperationalScope.CURRENT_OPERATIONAL_WEEK_MINE,
        OperationalScope.CURRENT_OPERATIONAL_WEEK_PLANT,
    }
)
_MONTHLY_OPERATIONAL_SCOPES = frozenset(
    {
        OperationalScope.CURRENT_OPERATIONAL_MONTH_MINE,
        OperationalScope.CURRENT_OPERATIONAL_MONTH_PLANT,
    }
)


class PiInterpolated:
    @staticmethod
    def latest(*, input_key: str, columns: tuple[DataColumn, ...]) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.PI_INTERPOLATED,
            view=DataView.LATEST,
            columns=columns,
        )

    @staticmethod
    def daily(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.PI_INTERPOLATED,
            view=DataView.DAILY,
            columns=columns,
            selection=_daily_selection(period),
        )

    @staticmethod
    def monthly(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.PI_INTERPOLATED,
            view=DataView.MONTHLY,
            columns=columns,
            selection=_monthly_selection(period),
        )


class PiRecorded:
    @staticmethod
    def daily(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.PI_RECORDED,
            view=DataView.DAILY,
            columns=columns,
            selection=_daily_selection(period),
        )

    @staticmethod
    def monthly(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.PI_RECORDED,
            view=DataView.MONTHLY,
            columns=columns,
            selection=_monthly_selection(period),
        )


class FabricaKpis:
    @staticmethod
    def daily(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.FABRICA_KPIS,
            view=DataView.DAILY,
            columns=columns,
            selection=_daily_selection(period),
        )

    @staticmethod
    def weekly(*, input_key: str, columns: tuple[DataColumn, ...]) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.FABRICA_KPIS,
            view=DataView.WEEKLY,
            columns=columns,
        )


class DispatchShiftLoads:
    @staticmethod
    def shift(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        selection: ShiftSelection,
    ) -> DataInputSpec:
        if not isinstance(selection, ShiftSelection):
            raise TypeError('selection must be ShiftSelection')
        return _input(
            input_key=input_key,
            source=DataSource.DISPATCH_STD_SHIFT_LOADS,
            view=DataView.SHIFT,
            columns=columns,
            selection=selection,
        )


class RemanentesStocks:
    @staticmethod
    def latest(*, input_key: str, columns: tuple[DataColumn, ...]) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.REMANENTES_STOCKS,
            view=DataView.LATEST,
            columns=columns,
        )


class MeteodataData:
    @staticmethod
    def daily(
        *,
        input_key: str,
        columns: tuple[DataColumn, ...],
        period: TimeWindow | OperationalScope,
    ) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.METEODATA_DATA,
            view=DataView.DAILY,
            columns=columns,
            selection=_daily_selection(period),
        )


def _input(
    *,
    input_key: str,
    source: DataSource,
    view: DataView,
    columns: tuple[DataColumn, ...],
    selection=None,
) -> DataInputSpec:
    return DataInputSpec(
        input_key=input_key,
        source=source,
        view=view,
        columns=columns,
        selection=selection,
    )


def _daily_selection(value: TimeWindow | OperationalScope):
    if isinstance(value, TimeWindow):
        if value.unit is TimeWindowUnit.MONTHS:
            raise ValueError('daily inputs do not accept month windows')
        return TimeWindowSelection(value)
    if isinstance(value, OperationalScope):
        if value not in _DAILY_OPERATIONAL_SCOPES:
            raise ValueError(f'{value.value}: operational scope does not use the daily view')
        return OperationalScopeSelection(value)
    raise TypeError('period must be TimeWindow or OperationalScope')


def _monthly_selection(value: TimeWindow | OperationalScope):
    if isinstance(value, TimeWindow):
        if value.unit is not TimeWindowUnit.MONTHS:
            raise ValueError('monthly inputs require month windows')
        return TimeWindowSelection(value)
    if isinstance(value, OperationalScope):
        if value not in _MONTHLY_OPERATIONAL_SCOPES:
            raise ValueError(f'{value.value}: operational scope does not use the monthly view')
        return OperationalScopeSelection(value)
    raise TypeError('period must be TimeWindow or OperationalScope')
