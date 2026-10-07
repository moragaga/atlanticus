from __future__ import annotations

from dataclasses import dataclass

from ada.alarms.core import AlarmResolutionKey


@dataclass(frozen=True, slots=True)
class DeliveryAlarmConfiguration:
    resolution_key: AlarmResolutionKey
    publication_tool_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        if not isinstance(self.publication_tool_keys, tuple):
            raise TypeError('publication_tool_keys must be a tuple')
        normalized: list[str] = []
        seen: set[str] = set()
        for tool_key in self.publication_tool_keys:
            _require_non_empty_string(tool_key, 'tool_key')
            if tool_key in seen:
                raise ValueError('publication_tool_keys must not contain duplicates')
            seen.add(tool_key)
            normalized.append(tool_key)
        object.__setattr__(self, 'publication_tool_keys', tuple(sorted(normalized)))


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')
