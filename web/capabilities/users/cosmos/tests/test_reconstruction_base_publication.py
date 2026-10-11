from __future__ import annotations

from dataclasses import replace

from atlanticus.connectivity.cosmos import CosmosConflictError
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.cosmos.store import CosmosUsersRuntimeStore
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    UserIdentity,
)


class MemoryCosmos:
    def __init__(self):
        self.items = {}
        self.writes = 0

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        value = self.items.get(item_id)
        return None if value is None else dict(value)

    def create_item(self, *, container_name, item, include_metadata=False):
        if item['id'] in self.items:
            raise CosmosConflictError('Duplicate')
        self.writes += 1
        self.items[item['id']] = dict(item, _etag=str(self.writes))
        return dict(self.items[item['id']])

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag=None, include_metadata=False):
        record = self.items[item_id]
        if record['_etag'] != if_match_etag:
            raise CosmosConflictError('Concurrent update')
        user = dict(record['user'])
        for operation in operations:
            assert operation.path.startswith('/user/')
            assert operation.path not in {'/user/access_keys', '/user/operational'}
            user[operation.path.removeprefix('/user/')] = operation.value
        self.writes += 1
        self.items[item_id] = dict(record, user=user, _etag=str(self.writes))
        return dict(self.items[item_id])


def _user():
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='alice'),
        issuer='issuer', subject_id='alice', display_name='Alice',
    )
    return RuntimeUser(
        identity=identity, enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        operational=RuntimeOperational(
            area=RuntimeOperationalReference(id='area', label='Area')
        ),
        access_keys=('dashboard.view',),
    )


def test_cosmos_base_reconstruction_preserves_existing_external_fields():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    original = _user()
    store.upsert_base_user(original)
    desired = replace(
        original, profile=RuntimeProfile.from_profile(ROOT_PROFILE),
        operational=RuntimeOperational(), access_keys=(),
    )
    result = store.upsert_base_user(desired)
    assert result.profile == desired.profile
    assert result.access_keys == original.access_keys
    assert result.operational == original.operational
    assert client.writes == 2
    store.upsert_base_user(desired)
    assert client.writes == 2
