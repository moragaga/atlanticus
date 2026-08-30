from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ContentStateDependencyError

# Las identidades de fuente y componente comparten una forma canónica estable.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


@dataclass(frozen=True, slots=True)
class ContentStateDependency:
    # Identidad estable del componente afectado.
    component_key: str
    # Fuentes que la capa de composición declaró como dependencias de degradación.
    source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_key(self.component_key, label='component key')
        normalized = tuple(self.source_keys)
        if not normalized:
            raise ContentStateDependencyError('Content State dependency requires source_keys')
        if len(set(normalized)) != len(normalized):
            raise ContentStateDependencyError('Content State dependency source_keys must be unique')
        for source_key in normalized:
            # El resolver valida identidad, no decide qué fuentes son CONTROL para una Tool.
            require_source_key(source_key)
        object.__setattr__(self, 'source_keys', normalized)


def require_source_key(source_key: str) -> str:
    # La autoridad CONTROL vive en Source Operational Participation, no en un catálogo local.
    _require_key(source_key, label='source key')
    return source_key


def require_component_key(component_key: str) -> str:
    # Las consultas por componente también deben usar identidad canónica.
    _require_key(component_key, label='component key')
    return component_key


def _require_key(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _KEY_PATTERN.fullmatch(value):
        raise ContentStateDependencyError(f'Invalid Content State {label}: {value!r}')
