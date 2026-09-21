from __future__ import annotations

from datetime import UTC, datetime

from ada.web.tools.configuration import ToolConfiguration
from ada_command_center.tools.catalog import (
    BlobToolCatalogStore,
    BlobToolCatalogStoreSettings,
    ToolCatalogEntry,
    create_tool_catalog_snapshot,
)
from atlanticus.connectivity.storage import StorageBlobNotFoundError, StorageClient
from atlanticus.web.source.models import SourceReleaseId

from .helpers import tool_configuration


class StorageClientStub(StorageClient):
    def __init__(self) -> None:
        self.payload: bytes | None = None
        self.uploads: list[dict[str, object]] = []

    def download(self, *, container_name: str, blob_name: str) -> bytes:
        del container_name, blob_name
        if self.payload is None:
            raise StorageBlobNotFoundError('missing')
        return self.payload

    def upload(
        self,
        *,
        container_name: str,
        blob_name: str,
        data,
        overwrite: bool = True,
        metadata=None,
        content_type: str | None = None,
    ) -> None:
        del metadata
        self.payload = bytes(data)
        self.uploads.append(
            {
                'container_name': container_name,
                'blob_name': blob_name,
                'overwrite': overwrite,
                'content_type': content_type,
            }
        )


def _snapshot():
    configuration: ToolConfiguration = tool_configuration()
    assert configuration.structure is not None
    return create_tool_catalog_snapshot(
        (
            ToolCatalogEntry(
                tool_key=configuration.tool_key,
                display_name=configuration.display_name,
                kind=configuration.kind,
                source_release_id=SourceReleaseId('release-1'),
                structure=configuration.structure,
            ),
        ),
        generated_at_utc=datetime(2026, 9, 21, 12, tzinfo=UTC),
    )


def test_blob_store_returns_none_when_current_catalog_does_not_exist() -> None:
    storage = StorageClientStub()
    store = BlobToolCatalogStore(
        storage=storage,
        settings=BlobToolCatalogStoreSettings(
            container_name='configuration',
            blob_name='command-center/tool-catalog/current.json',
        ),
    )

    assert store.get_current() is None


def test_blob_store_replaces_and_reads_current_catalog() -> None:
    storage = StorageClientStub()
    store = BlobToolCatalogStore(
        storage=storage,
        settings=BlobToolCatalogStoreSettings(
            container_name='configuration',
            blob_name='command-center/tool-catalog/current.json',
        ),
    )
    snapshot = _snapshot()

    replaced = store.replace_current(snapshot)
    restored = store.get_current()

    assert replaced == snapshot
    assert restored == snapshot
    assert storage.uploads == [
        {
            'container_name': 'configuration',
            'blob_name': 'command-center/tool-catalog/current.json',
            'overwrite': True,
            'content_type': 'application/json',
        }
    ]
