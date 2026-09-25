from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AlarmConfigurationSourceProvider(StrEnum):
    LOCAL = 'local'
    BLOB = 'blob'


class AlarmConfigurationProjectionProvider(StrEnum):
    LOCAL = 'local'
    COSMOS = 'cosmos'


@dataclass(frozen=True, slots=True)
class AlarmConfigurationPersistenceSettings:
    source_provider: AlarmConfigurationSourceProvider
    projection_provider: AlarmConfigurationProjectionProvider
    local_source_root: Path | None = None
    local_projection_root: Path | None = None
    blob_container_name: str | None = None
    blob_root_prefix: str = 'ada-command-center/alarms'
    cosmos_container_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_provider, AlarmConfigurationSourceProvider):
            raise TypeError('source_provider must be AlarmConfigurationSourceProvider')
        if not isinstance(self.projection_provider, AlarmConfigurationProjectionProvider):
            raise TypeError('projection_provider must be AlarmConfigurationProjectionProvider')
        if self.source_provider is AlarmConfigurationSourceProvider.LOCAL:
            object.__setattr__(
                self,
                'local_source_root',
                _absolute_root(self.local_source_root, 'local_source_root'),
            )
        if self.projection_provider is AlarmConfigurationProjectionProvider.LOCAL:
            object.__setattr__(
                self,
                'local_projection_root',
                _absolute_root(self.local_projection_root, 'local_projection_root'),
            )
        if self.source_provider is AlarmConfigurationSourceProvider.BLOB:
            object.__setattr__(
                self,
                'blob_container_name',
                _clean_text(self.blob_container_name, 'blob_container_name'),
            )
        if self.projection_provider is AlarmConfigurationProjectionProvider.COSMOS:
            object.__setattr__(
                self,
                'cosmos_container_name',
                _clean_text(self.cosmos_container_name, 'cosmos_container_name'),
            )


def _absolute_root(value: Path | None, field_name: str) -> Path:
    if value is None:
        raise ValueError(f'{field_name} is required by the local provider')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f'{field_name} must be absolute')
    return path


def _clean_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')
    if '\x00' in value:
        raise ValueError(f'{field_name} has an invalid format')
    return value
