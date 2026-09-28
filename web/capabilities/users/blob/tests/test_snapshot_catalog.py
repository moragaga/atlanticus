from datetime import UTC, datetime, timedelta

from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.blob.recovery import BlobApprovedUsersSnapshotStore


class Storage:
    def __init__(self):
        self.requests = []

    def list_blobs(self, *, container_name, prefix, max_items):
        self.requests.append((container_name, prefix, max_items))
        now = datetime.now(UTC)
        return (
            StorageBlobProperties('app/users/recovery/snapshots/old.json', 1, last_modified=now),
            StorageBlobProperties('app/users/recovery/snapshots/new.json', 1,
                                  last_modified=now + timedelta(minutes=1)),
            StorageBlobProperties('app/users/recovery/snapshots/nested/skip.json', 1),
            StorageBlobProperties('app/users/recovery/snapshots/_invalid.json', 1),
        )


def test_catalog_lists_only_snapshot_artifacts_in_recency_order():
    storage = Storage()
    snapshots = BlobApprovedUsersSnapshotStore(
        client=storage,
        container_name='lab',
        prefix='app/users/recovery/snapshots',
    )
    assert snapshots.list_snapshot_ids(max_items=20) == ('new', 'old')
    assert storage.requests == [('lab', 'app/users/recovery/snapshots/', 20)]


def test_history_uses_blob_save_date_without_downloading_snapshots():
    storage = Storage()
    snapshots = BlobApprovedUsersSnapshotStore(
        client=storage, container_name='lab', prefix='app/users/recovery/snapshots',
    )
    entries = snapshots.list_snapshot_summaries(max_items=20)
    assert tuple(entry[0] for entry in entries) == ('new', 'old')
    assert all(datetime.fromisoformat(entry[1]).tzinfo is not None for entry in entries)
    assert storage.requests == [('lab', 'app/users/recovery/snapshots/', 20)]
