from datetime import UTC, datetime

from atlanticus.connectivity.storage import StorageBlobNotFoundError, StorageConflictError
from atlanticus.connectivity.storage.models import StorageBlobProperties


class MemoryStorage:
    def __init__(self):
        self.data = {}
        self.etags = {}
        self.revision = 0

    def _etag(self, blob_name):
        return self.etags[blob_name]

    def get_properties(self, *, container_name, blob_name):
        if blob_name not in self.data:
            raise StorageBlobNotFoundError(blob_name)
        return StorageBlobProperties(
            name=blob_name,
            size=len(self.data[blob_name]),
            etag=self.etags[blob_name],
            last_modified=datetime.now(UTC),
        )

    def download(self, *, container_name, blob_name):
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
        return tuple(self.get_properties(container_name=container_name, blob_name=name) for name in names)

from datetime import UTC, datetime

import pytest

from atlanticus.web.users.blob.recovery import (
    BlobToolUsersRecoverySnapshotStore,
    BlobUsersRecoveryAuditStore,
    BlobUsersReplaceBeforeImageStore,
)
from atlanticus.web.users.recovery import (
    ToolUsersRecoverySnapshot,
    UsersRecoveryAuditEvent,
    UsersRecoveryConflictError,
    UsersReplaceBeforeImage,
)


def snapshot(snapshot_id='snapshot-1'):
    return ToolUsersRecoverySnapshot(
        snapshot_id=snapshot_id,
        origin_environment='local:test',
        captured_at_utc=datetime.now(UTC).isoformat(),
        operator_id='operator',
        approval_reference='ticket',
        users=(),
    )


def test_snapshot_store_is_tool_scoped_immutable_and_round_trips():
    storage = MemoryStorage()
    store = BlobToolUsersRecoverySnapshotStore(
        client=storage,
        container_name='configuration',
        prefix='app/tool/users/recovery/snapshots',
    )
    value = snapshot()
    store.save(value)
    assert store.load(value.snapshot_id) == value
    assert store.list_snapshot_ids() == (value.snapshot_id,)
    with pytest.raises(UsersRecoveryConflictError):
        store.save(value)


def test_before_image_and_audit_are_immutable_artifacts():
    storage = MemoryStorage()
    before = BlobUsersReplaceBeforeImageStore(
        client=storage,
        container_name='configuration',
        prefix='app/tool/users/recovery/replace-before',
    )
    audit = BlobUsersRecoveryAuditStore(
        client=storage,
        container_name='configuration',
        prefix='app/tool/users/recovery/audit',
    )
    before.save(
        UsersReplaceBeforeImage(
            operation_id='operation-1',
            snapshot_id='snapshot-1',
            captured_at_utc=datetime.now(UTC).isoformat(),
            users=(),
        )
    )
    audit.record(
        UsersRecoveryAuditEvent(
            operation_id='operation-1',
            snapshot_id='snapshot-1',
            stage='started',
            occurred_at_utc=datetime.now(UTC).isoformat(),
            operator_id='operator',
            approval_reference='ticket',
        )
    )
    assert 'app/tool/users/recovery/replace-before/operation-1.json' in storage.data
    assert 'app/tool/users/recovery/audit/operation-1-started.json' in storage.data
