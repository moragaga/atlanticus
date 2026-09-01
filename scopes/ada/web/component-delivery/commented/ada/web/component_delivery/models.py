from __future__ import annotations

import re
from dataclasses import dataclass

from ada.web.component_delivery.errors import ComponentDeliveryValidationError

# Delivery mantiene su validación de identidad local para no depender de helpers privados.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


@dataclass(frozen=True, slots=True)
class ComponentDelivery:
    # La dirección identifica un Store que ya debe existir. No crea estructura.
    tool_key: str
    component_key: str
    # None no representa una entrega: ausencia de delivery significa conservar el Store.
    payload: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'tool_key',
            _require_key(self.tool_key, label='Component Delivery tool key'),
        )
        object.__setattr__(
            self,
            'component_key',
            _require_key(self.component_key, label='Component Delivery component key'),
        )
        if self.payload is None:
            raise ComponentDeliveryValidationError(
                'Component Delivery payload must not be None'
            )


def _require_key(value: object, *, label: str) -> str:
    # Las keys siguen el mismo formato canónico de Tool y Component Store.
    if not isinstance(value, str):
        raise ComponentDeliveryValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ComponentDeliveryValidationError(f'{label} has an invalid format')
    return normalized
