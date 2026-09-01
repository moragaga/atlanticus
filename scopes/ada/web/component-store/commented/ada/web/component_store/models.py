from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ada.web.component_store.errors import ComponentStoreValidationError

# La identidad del Store usa el mismo formato canónico de keys que Tool Structure,
# pero el paquete no depende de helpers privados de ada.configuration.tools.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


class ComponentStoreState(StrEnum):
    # EMPTY significa ausencia de payload operacional.
    EMPTY = 'empty'
    # POPULATED significa solamente que existe un payload; no implica OK, salud ni validez UI.
    POPULATED = 'populated'


@dataclass(frozen=True, slots=True)
class ComponentStoreSnapshot:
    # La identidad siempre pertenece a una Tool y a uno de sus Components.
    tool_key: str
    component_key: str
    # Un Store contiene un único payload cohesivo.
    # None está reservado para representar el Store vacío.
    payload: object | None = None

    def __post_init__(self) -> None:
        # Normalizamos las identidades para que un Store no pueda divergir
        # del formato canónico utilizado por Tool Structure.
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
        # El estado se deriva del payload. Así no puede existir una combinación
        # inconsistente como state=EMPTY con un payload presente.
        if self.payload is None:
            return ComponentStoreState.EMPTY
        return ComponentStoreState.POPULATED

    @property
    def is_empty(self) -> bool:
        return self.payload is None


def _require_key(value: object, *, label: str) -> str:
    # Esta validación es deliberadamente local: Component Store no importa
    # utilidades privadas de Tool Configuration.
    if not isinstance(value, str):
        raise ComponentStoreValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ComponentStoreValidationError(f'{label} has an invalid format')
    return normalized
