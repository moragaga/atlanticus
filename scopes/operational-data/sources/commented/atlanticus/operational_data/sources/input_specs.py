# Espejo pedagógico de los builders orientados a fuente para DataInputSpec.
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

# Estos scopes se resuelven leyendo una vista DAILY y recortando el frame lógico en memoria.
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
# El mes operacional usa la vista MONTHLY; esto no describe el layout físico year/month.
_MONTHLY_OPERATIONAL_SCOPES = frozenset(
    {
        OperationalScope.CURRENT_OPERATIONAL_MONTH_MINE,
        OperationalScope.CURRENT_OPERATIONAL_MONTH_PLANT,
    }
)


# Expone solo las vistas válidas de PI interpolated y obliga a declarar período en históricos.
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


# Recorded no publica latest; por eso el builder ni siquiera ofrece ese método.
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


# Fábrica separa DAILY y WEEKLY como superficies lógicas diferentes.
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


# Dispatch shift trabaja por identificadores de turno y no por ventanas de tiempo genéricas.
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


# Remanentes stocks es una fuente latest-only en el contrato CURRENT.
class RemanentesStocks:
    @staticmethod
    def latest(*, input_key: str, columns: tuple[DataColumn, ...]) -> DataInputSpec:
        return _input(
            input_key=input_key,
            source=DataSource.REMANENTES_STOCKS,
            view=DataView.LATEST,
            columns=columns,
        )


# Meteodata datos es temporal y usa selección DAILY.
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


# Centraliza la creación del contrato neutral; los builders de fuente deciden qué combinaciones exponen.
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


# DAILY acepta ventanas inferiores a mes y scopes operacionales que se resuelven sobre datos diarios.
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


# MONTHLY acepta únicamente ventanas expresadas en meses o scopes operacionales mensuales.
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
