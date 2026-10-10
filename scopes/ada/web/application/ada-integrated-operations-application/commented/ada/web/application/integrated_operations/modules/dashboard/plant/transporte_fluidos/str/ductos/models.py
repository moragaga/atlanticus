from __future__ import annotations

# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.


from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import StrDuctDefinition, StrPumpDefinition


@dataclass(frozen=True, slots=True)
class StrPumpReading:
    definition: StrPumpDefinition
    state: DisplayValue


@dataclass(frozen=True, slots=True)
class StrDuctReading:
    definition: StrDuctDefinition
    state: DisplayValue
    solids_in: DisplayValue
    solids_out: DisplayValue
    pumps: tuple[StrPumpReading, ...]
