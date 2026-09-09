from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from ada.web.components.errors import (
    ComponentDeliveryValidationError,
    ComponentStoreValidationError,
)

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_ErrorT = TypeVar('_ErrorT', bound=ValueError)


def _require_key(value: object, *, label: str, error_type: type[_ErrorT]) -> str:
    if not isinstance(value, str):
        raise error_type(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise error_type(f'{label} has an invalid format')
    return normalized


class ComponentStoreState(StrEnum):
    EMPTY = 'empty'
    POPULATED = 'populated'


@dataclass(frozen=True, slots=True)
class ComponentStoreSnapshot:
    tool_key: str
    component_key: str
    payload: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'tool_key',
            _require_key(
                self.tool_key,
                label='Component Store tool key',
                error_type=ComponentStoreValidationError,
            ),
        )
        object.__setattr__(
            self,
            'component_key',
            _require_key(
                self.component_key,
                label='Component Store component key',
                error_type=ComponentStoreValidationError,
            ),
        )

    @property
    def state(self) -> ComponentStoreState:
        if self.payload is None:
            return ComponentStoreState.EMPTY
        return ComponentStoreState.POPULATED

    @property
    def is_empty(self) -> bool:
        return self.payload is None


@dataclass(frozen=True, slots=True)
class ComponentDelivery:
    tool_key: str
    component_key: str
    payload: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'tool_key',
            _require_key(
                self.tool_key,
                label='Component Delivery tool key',
                error_type=ComponentDeliveryValidationError,
            ),
        )
        object.__setattr__(
            self,
            'component_key',
            _require_key(
                self.component_key,
                label='Component Delivery component key',
                error_type=ComponentDeliveryValidationError,
            ),
        )
        if self.payload is None:
            raise ComponentDeliveryValidationError('Component Delivery payload must not be None')
