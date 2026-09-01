from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ada.web.component_store.errors import ComponentStoreValidationError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


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
            _require_key(self.tool_key, label='Component Store tool key'),
        )
        object.__setattr__(
            self,
            'component_key',
            _require_key(self.component_key, label='Component Store component key'),
        )

    @property
    def state(self) -> ComponentStoreState:
        if self.payload is None:
            return ComponentStoreState.EMPTY
        return ComponentStoreState.POPULATED

    @property
    def is_empty(self) -> bool:
        return self.payload is None


def _require_key(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ComponentStoreValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ComponentStoreValidationError(f'{label} has an invalid format')
    return normalized
