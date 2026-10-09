from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue


# Separar el origen del KPI de su valor permite inspección individual y estados independientes.
@dataclass(frozen=True, slots=True)
class LeyesMetric:
    kpi_key: str
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class LeyesRow:
    key: str
    label: str
    hora: LeyesMetric
    turno: LeyesMetric
    dia: LeyesMetric
    plan: LeyesMetric


@dataclass(frozen=True, slots=True)
# El orden de las filas corresponde a la definición operacional de Leyes.
class LeyesState:
    rows: tuple[LeyesRow, ...]
