from __future__ import annotations

# Contratos inmutables: puntos ordenados en UTC y huecos representados por None.
# La zona horaria de pantalla no se guarda ni modifica el valor temporal.
from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import AlimentadoTrendDefinition


@dataclass(frozen=True, slots=True)
class AlimentadoTrendReading:
    definition: AlimentadoTrendDefinition
    current: DisplayValue
    history: TimeSeriesValues
