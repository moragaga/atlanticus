from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from atlanticus.operational_data.core.errors import DataInputNotRequestedError


# Interfaz mínima que debe exponer cada frame entregado a un consumidor.
@runtime_checkable
class RuntimeFrameContext(Protocol):
    @property
    def dataframe(self) -> Any: ...

    def last_row(self) -> Any: ...

    def last_value(self, column: str, default: Any = None) -> Any: ...

    def last_value_number(self, column: str, default: float | None = None) -> float | None: ...


# Contexto final: el consumidor accede exclusivamente por su input_key local.
@dataclass(frozen=True, slots=True)
class DataInputContext:
    frames: Mapping[str, RuntimeFrameContext]

    def __post_init__(self) -> None:
        normalized: dict[str, RuntimeFrameContext] = {}
        for input_key, frame in self.frames.items():
            if not isinstance(input_key, str) or not input_key:
                raise ValueError('data input context keys must be non-empty strings')
            if input_key != input_key.strip():
                raise ValueError('data input context keys must not contain surrounding whitespace')
            if not isinstance(frame, RuntimeFrameContext):
                raise TypeError(f'{input_key}: invalid runtime frame')
            normalized[input_key] = frame
        object.__setattr__(self, 'frames', MappingProxyType(normalized))

    @property
    def input_keys(self) -> tuple[str, ...]:
        return tuple(self.frames)

    def get(self, input_key: str) -> RuntimeFrameContext:
        if not isinstance(input_key, str) or not input_key:
            raise ValueError('input_key must be a non-empty string')
        if input_key != input_key.strip():
            raise ValueError('input_key must not contain surrounding whitespace')
        try:
            return self.frames[input_key]
        except KeyError as error:
            raise DataInputNotRequestedError(
                f'{input_key}: data input was not requested'
            ) from error
