from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.feeder import FeederColor


# Los valores se conservan como datos numéricos; el color solo condiciona la presentación.
@dataclass(frozen=True, slots=True)
class ChacayFeederReading:
    value: DisplayValue
    color: FeederColor | None = None
