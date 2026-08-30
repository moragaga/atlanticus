from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ContentStateDependencyError

# Las keys siguen la misma forma canónica usada por la identidad DOM ADA.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
# Sólo PI y Dispatch poseen autoridad operacional para degradar componentes en ADA.
_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


@dataclass(frozen=True, slots=True)
class ContentStateDependency:
    # Identidad estable del componente afectado; no se crea una state_key paralela.
    component_key: str
    # Fuentes de control requeridas por este componente.
    source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_key(self.component_key, label='component key')
        normalized = tuple(self.source_keys)
        if not normalized:
            raise ContentStateDependencyError('Content State dependency requires source_keys')
        if len(set(normalized)) != len(normalized):
            raise ContentStateDependencyError('Content State dependency source_keys must be unique')
        for source_key in normalized:
            _require_control_source_key(source_key)
        object.__setattr__(self, 'source_keys', normalized)


def require_control_source_key(source_key: str) -> str:
    # Se expone para que el grafo aplique exactamente la misma validación en consultas y snapshots.
    _require_control_source_key(source_key)
    return source_key


def require_component_key(component_key: str) -> str:
    # Las consultas por componente también deben usar identidad canónica.
    _require_key(component_key, label='component key')
    return component_key


def _require_control_source_key(source_key: str) -> None:
    _require_key(source_key, label='source key')
    if source_key not in _CONTROL_SOURCE_KEYS:
        raise ContentStateDependencyError(
            f'Unsupported Content State control source: {source_key!r}'
        )


def _require_key(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _KEY_PATTERN.fullmatch(value):
        raise ContentStateDependencyError(f'Invalid Content State {label}: {value!r}')
