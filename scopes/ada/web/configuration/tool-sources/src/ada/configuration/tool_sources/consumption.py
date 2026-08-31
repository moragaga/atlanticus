from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.configuration.tool_sources.errors import ToolSourceConsumptionValidationError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


@dataclass(frozen=True, slots=True)
class ToolSourceConsumption:
    tool_key: str
    source_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tool_key = _require_key(self.tool_key, label='Tool key')
        if isinstance(self.source_keys, (str, bytes)):
            raise ToolSourceConsumptionValidationError(
                'Tool source keys must be a collection of source keys'
            )
        try:
            source_keys = tuple(
                _require_key(source_key, label='Source key') for source_key in self.source_keys
            )
        except TypeError as error:
            raise ToolSourceConsumptionValidationError(
                'Tool source keys must be a collection of source keys'
            ) from error
        if len(source_keys) != len(set(source_keys)):
            raise ToolSourceConsumptionValidationError('Tool source keys must be unique')
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'source_keys', source_keys)

    def consumes(self, source_key: str) -> bool:
        return _require_key(source_key, label='Source key') in self.source_keys

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'source_keys': list(self.source_keys),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolSourceConsumption:
        try:
            source_keys = document['source_keys']
            if not isinstance(source_keys, list):
                raise TypeError
            return cls(
                tool_key=document['tool_key'],
                source_keys=tuple(source_keys),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolSourceConsumptionValidationError):
                raise
            raise ToolSourceConsumptionValidationError(
                'Tool source consumption contract is invalid'
            ) from error


def _require_key(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ToolSourceConsumptionValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ToolSourceConsumptionValidationError(f'{label} has an invalid format')
    return normalized
