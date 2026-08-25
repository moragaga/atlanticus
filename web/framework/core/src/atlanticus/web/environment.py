from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from atlanticus.web.errors import WebConfigurationError

_ENVIRONMENT_VARIABLE = 'ATLANTICUS_ENVIRONMENT'


class EnvironmentReader:
    __slots__ = ('_values',)

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        source = os.environ if values is None else values
        if not isinstance(source, Mapping):
            raise TypeError('values must be a mapping or None')
        copied: dict[str, str] = {}
        for name, value in source.items():
            _validate_variable_name(name)
            if not isinstance(value, str):
                raise TypeError(f"Environment variable '{name}' must contain text")
            copied[name] = value
        self._values = MappingProxyType(copied)

    def optional(self, name: str) -> str | None:
        normalized = _validate_variable_name(name)
        return self._values.get(normalized)

    def require(self, name: str) -> str:
        normalized = _validate_variable_name(name)
        value = self._values.get(normalized)
        if value is None or value == '':
            raise WebConfigurationError(
                f"Required environment variable '{normalized}' is not available"
            )
        return value


class WebEnvironment(StrEnum):
    LOCAL = 'local'
    PRODUCTION = 'production'

    @property
    def is_local(self) -> bool:
        return self is WebEnvironment.LOCAL

    @property
    def is_production(self) -> bool:
        return self is WebEnvironment.PRODUCTION


def resolve_environment(values: Mapping[str, str] | None = None) -> WebEnvironment:
    source = os.environ if values is None else values
    raw_value = source.get(_ENVIRONMENT_VARIABLE, WebEnvironment.LOCAL.value)
    normalized = raw_value.strip().lower()

    try:
        return WebEnvironment(normalized)
    except ValueError as exc:
        raise WebConfigurationError(
            f'Invalid {_ENVIRONMENT_VARIABLE}: expected local or production'
        ) from exc


def _validate_variable_name(name: object) -> str:
    if not isinstance(name, str) or not name or not name.strip():
        raise TypeError('Environment variable name must be non-empty text')
    if name != name.strip() or '=' in name or '\x00' in name:
        raise ValueError('Environment variable name is invalid')
    return name
