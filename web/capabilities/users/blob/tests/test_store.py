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

from atlanticus.web.users.blob.store import BlobToolMembershipStore, BlobUsersRegistryStore
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import ToolUserMembership, UserIdentity


def identity():
    return UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='subject'),
        issuer='issuer',
        subject_id='subject',
        display_name='User',
        email='user@example.com',
    )


def test_global_registry_persists_identity_only():
    storage = MemoryStorage()
    store = BlobUsersRegistryStore(
        client=storage,
        container_name='configuration',
        blob_name='app/users/users.json.gz',
    )
    assert store.load().users == ()
    user = identity()
    saved = store.replace((user,), expected_version=None)
    assert saved.users == (user,)
    assert saved.version is not None
    assert store.load().users == (user,)


def test_tool_membership_is_separate_blob_and_uses_etag():
    storage = MemoryStorage()
    store = BlobToolMembershipStore(
        client=storage,
        container_name='configuration',
        blob_name='app/tool/users/memberships.json.gz',
    )
    user = identity()
    membership = ToolUserMembership(user_id=user.user_id, profile_key='root')
    saved = store.replace((membership,), expected_version=None)
    assert saved.memberships == (membership,)
    updated = ToolUserMembership(user_id=user.user_id, profile_key='basic', enabled=False)
    saved2 = store.replace((updated,), expected_version=saved.version)
    assert saved2.memberships == (updated,)
