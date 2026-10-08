# Un equipo consume el contrato DisplayValue compartido. El estado operacional es un valor OK y los estados degradados se mantienen separados.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.web.ui.display_status import DisplayStatus, DisplayValue


class LabelPosition(StrEnum):
    TOP = 'top'
    BOTTOM = 'bottom'
    LEFT = 'left'
    RIGHT = 'right'


@dataclass(frozen=True, slots=True)
class EquipmentStateImage:
    image: str
    state: DisplayValue
    label: str | None = None
    label_position: LabelPosition = LabelPosition.TOP
    label_class_name: str | None = None
    image_class_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image, str) or not self.image.strip():
            raise ValueError('Equipment image identifier cannot be empty')
        object.__setattr__(self, 'image', self.image.strip())
        if not isinstance(self.state, DisplayValue):
            raise TypeError('Equipment image state must be DisplayValue')
        if not isinstance(self.state.status, DisplayStatus):
            raise TypeError('Equipment image status must be DisplayStatus')
        if self.label is not None:
            if not isinstance(self.label, str) or not self.label.strip():
                raise ValueError('Equipment image label must be null or a non-empty string')
            object.__setattr__(self, 'label', self.label.strip())
        if not isinstance(self.label_position, LabelPosition):
            raise TypeError('Equipment image label_position must be LabelPosition')
        for name in ('label_class_name', 'image_class_name'):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f'Equipment image {name} must be null or a non-empty string')
                object.__setattr__(self, name, value.strip())
