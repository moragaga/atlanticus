from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.web.users.cosmos.store import CosmosUsersStore
from atlanticus.web.users.errors import UsersStoreUnavailableError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord


def user(subject: str, *, profile_key: str = 'basic') -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra',
        subject_id=subject,
        display_name=f'User {subject}',
        email=None,
        enabled=True,
        profile_key=profile_key,
    )


class FakeCosmos:
    def __init__(self):
        self.documents = {}
        self.sequence = 0
        self.deleted = []

    def _next_version(self):
        self.sequence += 1
        return f'version-{self.sequence}'

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        assert partition_key == item_id
        value = self.documents.get(item_id)
        return None if value is None else self._copy(value, include_metadata)

    def create_item(self, *, container_name, item, include_metadata=False):
        assert item['id'] not in self.documents
        value = {**item, '_etag': self._next_version()}
        self.documents[item['id']] = value
        return self._copy(value, include_metadata)

    def patch_item(
        self, *, container_name, item_id, partition_key, operations,
        if_match_etag=None, include_metadata=False,
    ):
        document = self.documents[item_id]
        assert document['_etag'] == if_match_etag
        for operation in operations:
            document[operation.path[1:]] = operation.value
        document['_etag'] = self._next_version()
        return self._copy(document, include_metadata)

    def query_items(
        self, *, container_name, query, parameters=None,
        cross_partition=False, include_metadata=False,
    ):
        assert cross_partition is True
        assert parameters[0].value == 'atlanticus_user'
        return tuple(
            self._copy(document, include_metadata)
            for document in self.documents.values()
            if document['document_type'] == 'atlanticus_user'
        )

    def delete_item(self, *, container_name, item_id, partition_key, if_match_etag=None):
        assert item_id == partition_key
        assert self.documents[item_id]['_etag'] == if_match_etag
        self.deleted.append((item_id, if_match_etag))
        del self.documents[item_id]

    @staticmethod
    def _copy(document, include_metadata):
        return {
            key: value for key, value in document.items()
            if include_metadata or key != '_etag'
        }


def test_cosmos_replacement_uses_real_item_versions_and_preserves_container():
    client = FakeCosmos()
    store = CosmosUsersStore(client=client, container_name='users-runtime')
    old, extra = user('old'), user('extra')
    store.create(old)
    store.create(extra)
    versions = {entry.user.user_id: entry.version for entry in store.list_versioned_users()}
    updated = replace(old, profile_key='root')
    assert store.replace_if_version(updated, expected_version=versions[old.user_id]) == updated
    store.delete_if_version(extra.user_id, expected_version=versions[extra.user_id])
    assert [entry.user for entry in store.list_versioned_users()] == [updated]
    assert client.deleted == [(extra.user_id, versions[extra.user_id])]
    assert set(client.documents) == {old.user_id}


def test_cosmos_replacement_rejects_stale_versions_without_mutating():
    client = FakeCosmos()
    store = CosmosUsersStore(client=client, container_name='users-runtime')
    saved = user('selected')
    store.create(saved)
    version = store.list_versioned_users()[0].version
    client.documents[saved.user_id]['_etag'] = 'concurrent-version'
    with pytest.raises(UsersStoreUnavailableError, match='changed'):
        store.replace_if_version(replace(saved, profile_key='root'), expected_version=version)
    with pytest.raises(UsersStoreUnavailableError, match='changed'):
        store.delete_if_version(saved.user_id, expected_version=version)
    assert store.get(saved.user_id) == saved
    assert not client.deleted
