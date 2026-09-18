from __future__ import annotations

import pytest

from atlanticus.connectivity.storage import StorageBlobNotFoundError, StorageConflictError
from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY
from atlanticus.web.users.blob import BlobUsersRegistryStore
from atlanticus.web.users.errors import UsersRegistryConflictError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord


def user(subject: str) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra', subject_id=subject, display_name=f'User {subject}',
        email=None, enabled=True, authority_key=BASIC_AUTHORITY_KEY,
    )


class FakeStorage:
    def __init__(self):
        self.data = None
        self.etag = None
        self.sequence = 0

    def _props(self):
        if self.data is None:
            raise StorageBlobNotFoundError
        return StorageBlobProperties(name='users/users.json.gz', size=len(self.data), etag=self.etag)

    def get_properties(self, *, container_name, blob_name):
        assert container_name == 'container'
        assert blob_name == 'users/users.json.gz'
        return self._props()

    def download(self, *, container_name, blob_name):
        self._props()
        return self.data

    def upload(self, *, container_name, blob_name, data, overwrite=True, metadata=None, content_type=None):
        if self.data is not None and not overwrite:
            raise StorageConflictError
        self.data = bytes(data)
        self.sequence += 1
        self.etag = f'e{self.sequence}'
        assert content_type == 'application/gzip'

    def upload_if_match(self, *, container_name, blob_name, data, etag, metadata=None, content_type=None):
        if self.etag != etag:
            raise StorageConflictError
        self.data = bytes(data)
        self.sequence += 1
        self.etag = f'e{self.sequence}'
        assert content_type == 'application/gzip'


def test_blob_registry_roundtrip_and_etag_concurrency():
    client = FakeStorage()
    store = BlobUsersRegistryStore(client=client, container_name='container')
    empty = store.load()
    assert empty.users == ()
    assert empty.version is None
    first = store.replace((user('1'),), expected_version=None)
    assert first.version == 'e1'
    loaded = store.load()
    assert loaded == first
    second = store.replace((user('1'), user('2')), expected_version='e1')
    assert second.version == 'e2'
    with pytest.raises(UsersRegistryConflictError):
        store.replace((user('1'),), expected_version='e1')
