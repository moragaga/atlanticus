from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ada.web.storage.namespace import AdaStorageNamespace


class ToolSourceProvider(StrEnum):
    LOCAL = 'local'
    BLOB = 'blob'


class ToolProjectionProvider(StrEnum):
    LOCAL = 'local'
    COSMOS = 'cosmos'


class ToolProjectionResolutionState(StrEnum):
    READY = 'ready'
    UNCONFIGURED = 'unconfigured'
    UNAVAILABLE = 'unavailable'
    INVALID = 'invalid'


@dataclass(frozen=True, slots=True)
class ToolPersistenceSettings:
    namespace: AdaStorageNamespace
    source_provider: ToolSourceProvider
    projection_provider: ToolProjectionProvider
    local_base_root: Path | None = None
    blob_container_name: str | None = None
    cosmos_container_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, AdaStorageNamespace):
            raise TypeError('namespace must be AdaStorageNamespace')
        if not isinstance(self.source_provider, ToolSourceProvider):
            raise TypeError('source_provider must be ToolSourceProvider')
        if not isinstance(self.projection_provider, ToolProjectionProvider):
            raise TypeError('projection_provider must be ToolProjectionProvider')

        local_base_root = self.local_base_root
        if local_base_root is not None:
            local_base_root = Path(local_base_root).expanduser()
            if not local_base_root.is_absolute():
                raise ValueError('local_base_root must be an absolute path')
            object.__setattr__(self, 'local_base_root', local_base_root)

        if (
            self.source_provider is ToolSourceProvider.LOCAL
            or self.projection_provider is ToolProjectionProvider.LOCAL
        ) and local_base_root is None:
            raise ValueError('local_base_root is required by a local provider')

        if self.source_provider is ToolSourceProvider.BLOB:
            object.__setattr__(
                self,
                'blob_container_name',
                _require_clean_text(
                    self.blob_container_name,
                    'blob_container_name',
                ),
            )

        if self.projection_provider is ToolProjectionProvider.COSMOS:
            object.__setattr__(
                self,
                'cosmos_container_name',
                _require_clean_text(
                    self.cosmos_container_name,
                    'cosmos_container_name',
                ),
            )


def _require_clean_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    if not value or not value.strip() or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')
    if '\x00' in value:
        raise ValueError(f'{field_name} has an invalid format')
    return value
