from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ConfigurationMutationStatus(StrEnum):
    IDLE = 'idle'
    SAVING = 'saving'
    DELETING = 'deleting'
    CONFLICT = 'conflict'
    ERROR = 'error'


@dataclass(frozen=True, slots=True)
class ConfigurationMutationState:
    status: ConfigurationMutationStatus = ConfigurationMutationStatus.IDLE
    item_key: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConfigurationMutationStatus):
            raise ValueError('Configuration mutation status is invalid')
        item_key = self.item_key.strip() if isinstance(self.item_key, str) else self.item_key
        if item_key == '':
            item_key = None
        if item_key is not None and not isinstance(item_key, str):
            raise ValueError('Configuration mutation item key must be text or null')
        if self.message is not None and not isinstance(self.message, str):
            raise ValueError('Configuration mutation message must be text or null')
        if self.status in {
            ConfigurationMutationStatus.SAVING,
            ConfigurationMutationStatus.DELETING,
            ConfigurationMutationStatus.CONFLICT,
        } and item_key is None:
            raise ValueError('Configuration mutation state requires an item key')
        object.__setattr__(self, 'item_key', item_key)

    @property
    def busy(self) -> bool:
        return self.status in {
            ConfigurationMutationStatus.SAVING,
            ConfigurationMutationStatus.DELETING,
        }

    def blocks(self, item_key: str) -> bool:
        return self.busy and self.item_key == item_key
