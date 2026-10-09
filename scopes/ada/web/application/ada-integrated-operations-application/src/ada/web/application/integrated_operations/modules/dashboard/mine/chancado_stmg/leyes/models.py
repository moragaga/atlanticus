from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue


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
class LeyesState:
    rows: tuple[LeyesRow, ...]
