from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import SelectivaIndicatorDefinition


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: SelectivaIndicatorReading; mantiene el mismo contrato que producción.
class SelectivaIndicatorReading:
    definition: SelectivaIndicatorDefinition
    value: DisplayValue
