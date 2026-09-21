from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.tools.catalog.codec import tool_catalog_from_bytes, tool_catalog_to_bytes
from ada_command_center.tools.catalog.errors import ToolCatalogStoreError
from ada_command_center.tools.catalog.models import ToolCatalogSnapshot
from ada_command_center.tools.catalog.store import ToolCatalogStore
from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageClient,
    StorageError,
)


@dataclass(frozen=True, slots=True)
class BlobToolCatalogStoreSettings:
    container_name: str
    blob_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'container_name',
            _require_clean_text(self.container_name, 'container_name'),
        )
        object.__setattr__(
            self,
            'blob_name',
            _require_clean_text(self.blob_name, 'blob_name'),
        )


class BlobToolCatalogStore(ToolCatalogStore):
    def __init__(
        self,
        *,
        storage: StorageClient,
        settings: BlobToolCatalogStoreSettings,
    ) -> None:
        if not isinstance(storage, StorageClient):
            raise TypeError('storage must be StorageClient')
        if not isinstance(settings, BlobToolCatalogStoreSettings):
            raise TypeError('settings must be BlobToolCatalogStoreSettings')
        self._storage = storage
        self._settings = settings

    def get_current(self) -> ToolCatalogSnapshot | None:
        try:
            payload = self._storage.download(
                container_name=self._settings.container_name,
                blob_name=self._settings.blob_name,
            )
        except StorageBlobNotFoundError:
            return None
        except StorageError as error:
            raise ToolCatalogStoreError('Could not read Tool Catalog from Storage') from error
        return tool_catalog_from_bytes(payload)

    def replace_current(self, snapshot: ToolCatalogSnapshot) -> ToolCatalogSnapshot:
        try:
            self._storage.upload(
                container_name=self._settings.container_name,
                blob_name=self._settings.blob_name,
                data=tool_catalog_to_bytes(snapshot),
                overwrite=True,
                content_type='application/json',
            )
        except StorageError as error:
            raise ToolCatalogStoreError('Could not write Tool Catalog to Storage') from error
        return snapshot


def _require_clean_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    if not value or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')
    if any(character in value for character in '\x00\r\n'):
        raise ValueError(f'{field_name} has an invalid format')
    return value
