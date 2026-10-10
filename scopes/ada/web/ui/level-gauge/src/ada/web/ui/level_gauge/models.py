from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch
from typing import Literal

from ada.web.ui.display_status import DisplayValue

LevelImage = Literal['tk', 'st']


@dataclass(frozen=True, slots=True)
class LevelGaugeView:
    label: str
    image: LevelImage
    level: DisplayValue
    state: DisplayValue
    unit: str = '%'
    state_override: Literal['operando', 'detenido'] | None = None
    fill_color: str = '#5b5c64'
    tone: Literal['default', 'warning', 'danger'] = 'default'

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Level gauge label cannot be empty')
        if self.image not in ('tk', 'st'):
            raise ValueError('Unsupported level gauge image')
        if not isinstance(self.level, DisplayValue) or not isinstance(self.state, DisplayValue):
            raise TypeError('Level gauge readings must be DisplayValue')
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError('Level gauge unit cannot be empty')
        if self.state_override is not None and self.state_override not in ('operando', 'detenido'):
            raise ValueError('Unsupported level gauge state override')
        if not isinstance(self.fill_color, str) or not fullmatch(r'#[0-9a-fA-F]{6}', self.fill_color):
            raise ValueError('Level gauge fill_color must be a six-digit hex color')
        if self.tone not in ('default', 'warning', 'danger'):
            raise ValueError('Unsupported level gauge tone')
