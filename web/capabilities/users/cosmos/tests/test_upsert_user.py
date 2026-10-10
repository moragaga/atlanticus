from dataclasses import replace

import pytest

from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosItemNotFoundError
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore
from atlanticus.web.users.errors import UsersDefinitionError, UsersStoreUnavailableError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


class MemoryCosmos:
    def __init__(self):
        self.items = {}
        self.writes = 0
        self.conflict_on_patch = False

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        record = self.items.get(item_id)
        return None if record is None else dict(record)

    def create_item(self, *, container_name, item, include_metadata=False):
        if item['id'] in self.items:
            raise CosmosConflictError('duplicate')
        self.writes += 1
        record = dict(item, _etag=f'etag-{self.writes}')
        self.items[item['id']] = record
        return dict(record)

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag=None, include_metadata=False):
        record = self.items.get(item_id)
        if record is None:
            raise CosmosItemNotFoundError('missing')
        if self.conflict_on_patch or record['_etag'] != if_match_etag:
            raise CosmosConflictError('stale')
        updated = dict(record)
        for operation in operations:
            assert operation.operation == 'set'
            updated[operation.path.removeprefix('/')] = operation.value
        self.writes += 1
        updated['_etag'] = f'etag-{self.writes}'
        self.items[item_id] = updated
        return dict(updated)


def _runtime(subject: str, *, root: bool = False) -> RuntimeUser:
    issuer = 'issuer'
    identity = UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject),
        issuer=issuer,
        subject_id=subject,
        display_name=subject,
    )
    return RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE if root else BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )


def test_upsert_creates_only_the_requested_user_and_round_trips():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    user_a = _runtime('a')
    user_b = _runtime('b')

    assert store.upsert_user(user_a) == user_a
    assert store.upsert_user(user_b) == user_b
    assert client.writes == 2
    assert client.items[user_a.user_id]['schema_version'] == 2
    assert client.items[user_b.user_id]['user']['access_keys'] == ['dashboard.view']


def test_upsert_changes_one_document_and_is_idempotent():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    first = _runtime('a')
    other = _runtime('b')
    store.upsert_user(first)
    store.upsert_user(other)
    before_other = dict(client.items[other.user_id])
    changed = replace(first, profile=RuntimeProfile.from_profile(ROOT_PROFILE))

    assert store.upsert_user(changed) == changed
    assert store.upsert_user(changed) == changed
    assert client.writes == 3
    assert client.items[other.user_id] == before_other


def test_upsert_detects_concurrent_modification():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    user = _runtime('a')
    store.upsert_user(user)
    client.conflict_on_patch = True

    with pytest.raises(UsersStoreUnavailableError, match='concurrently'):
        store.upsert_user(replace(user, enabled=False))
    assert client.items[user.user_id]['user']['enabled'] is True


def test_upsert_refuses_incompatible_existing_document():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    user = _runtime('a')
    store.upsert_user(user)
    client.items[user.user_id]['schema_version'] = 1

    with pytest.raises(UsersDefinitionError, match='schema version'):
        store.upsert_user(user)


def test_upsert_rejects_invalid_input():
    store = CosmosUsersRuntimeStore(client=MemoryCosmos(), container_name='users-runtime')
    with pytest.raises(TypeError):
        store.upsert_user(object())
