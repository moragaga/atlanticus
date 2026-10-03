from datetime import UTC, datetime

from atlanticus.web.users.blob.recovery import BlobToolUsersRecoverySnapshotStore
from atlanticus.web.users.recovery import ToolUsersRecoverySnapshot


class MemoryStorage:
    def __init__(self):
        self.data = {}
        self.etags = {}
        self.revision = 0

    def get_properties(self, *, container_name, blob_name):
        from atlanticus.connectivity.storage import StorageBlobNotFoundError
        from atlanticus.connectivity.storage.models import StorageBlobProperties

        if blob_name not in self.data:
            raise StorageBlobNotFoundError(blob_name)
        return StorageBlobProperties(
            name=blob_name,
            size=len(self.data[blob_name]),
            etag=self.etags[blob_name],
            last_modified=datetime.now(UTC),
        )

    def download(self, *, container_name, blob_name):
        from atlanticus.connectivity.storage import StorageBlobNotFoundError

        if blob_name not in self.data:
            raise StorageBlobNotFoundError(blob_name)
        return self.data[blob_name]

    def upload(
        self,
        *,
        container_name,
        blob_name,
        data,
        overwrite=True,
        metadata=None,
        content_type=None,
    ):
        from atlanticus.connectivity.storage import StorageConflictError

        if not overwrite and blob_name in self.data:
            raise StorageConflictError(blob_name)
        self.revision += 1
        self.data[blob_name] = bytes(data)
        self.etags[blob_name] = f'e{self.revision}'

    def upload_if_match(
        self,
        *,
        container_name,
        blob_name,
        data,
        etag,
        metadata=None,
        content_type=None,
    ):
        from atlanticus.connectivity.storage import StorageConflictError

        if blob_name not in self.data or self.etags[blob_name] != etag:
            raise StorageConflictError(blob_name)
        self.revision += 1
        self.data[blob_name] = bytes(data)
        self.etags[blob_name] = f'e{self.revision}'

    def list_blobs(self, *, container_name, prefix=None, max_items=None):
        names = sorted(
            name for name in self.data if prefix is None or name.startswith(prefix)
        )
        if max_items is not None:
            names = names[:max_items]
        return tuple(
            self.get_properties(container_name=container_name, blob_name=name)
            for name in names
        )


def test_snapshot_catalog_lists_saved_tool_snapshots():
    storage = MemoryStorage()
    store = BlobToolUsersRecoverySnapshotStore(
        client=storage,
        container_name='configuration',
        prefix='app/tool/users/recovery/snapshots',
    )
    for snapshot_id in ('one', 'two'):
        store.save(
            ToolUsersRecoverySnapshot(
                snapshot_id=snapshot_id,
                origin_environment='local:test',
                captured_at_utc=datetime.now(UTC).isoformat(),
                operator_id='operator',
                approval_reference='ticket',
                users=(),
            )
        )
    assert set(store.list_snapshot_ids()) == {'one', 'two'}
