from __future__ import annotations

from dataclasses import replace
from copy import deepcopy

import pytest

from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosPreconditionFailedError
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.cosmos.store import CosmosUsersRuntimeStore
from atlanticus.web.users.errors import UsersIdentityConflictError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


class Cosmos:
    def __init__(self):
        self.items = {}
        self.etag = 0
        self.race = False

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        assert item_id == partition_key
        document = self.items.get(item_id)
        return None if document is None else deepcopy(document)

    def create_item(self, *, container_name, item, include_metadata=False):
        if item['id'] in self.items:
            raise CosmosConflictError('Duplicate')
        self.etag += 1
        self.items[item['id']] = dict(deepcopy(item), _etag=str(self.etag))
        return deepcopy(self.items[item['id']])

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag=None, include_metadata=False):
        assert item_id == partition_key
        if self.race:
            self.race = False
            self.etag += 1
            self.items[item_id]['_etag'] = str(self.etag)
            self.items[item_id]['user']['access_keys'] = ['critical.new']
        document = self.items[item_id]
        if if_match_etag != document['_etag']:
            raise CosmosPreconditionFailedError('Concurrent edit')
        assert len(operations) == 1
        assert operations[0].path == '/user'
        self.etag += 1
        self.items[item_id] = dict(document, user=deepcopy(operations[0].value), _etag=str(self.etag))
        return deepcopy(self.items[item_id])


def _user():
    issuer, subject = 'issuer', 'alice'
    identity = UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject),
        issuer=issuer, subject_id=subject, display_name='Alice',
    )
    return RuntimeUser(
        identity=identity, enabled=True, profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )


def test_conditional_publication_creates_and_updates_entire_user():
    cosmos = Cosmos()
    store = CosmosUsersRuntimeStore(client=cosmos, container_name='users-runtime')
    initial = _user()
    assert store.upsert_user_if_current(initial, expected=None) == initial
    desired = replace(initial, profile=RuntimeProfile.from_profile(ROOT_PROFILE), access_keys=('reports.view',))
    assert store.upsert_user_if_current(desired, expected=initial) == desired
    assert cosmos.items[initial.user_id]['user']['access_keys'] == ['reports.view']


def test_conditional_publication_preserves_concurrent_access_write():
    cosmos = Cosmos()
    store = CosmosUsersRuntimeStore(client=cosmos, container_name='users-runtime')
    original = _user()
    store.upsert_user_if_current(original, expected=None)
    cosmos.race = True
    desired = replace(original, profile=RuntimeProfile.from_profile(ROOT_PROFILE))
    with pytest.raises(UsersIdentityConflictError, match='changed'):
        store.upsert_user_if_current(desired, expected=original)
    assert cosmos.items[original.user_id]['user']['access_keys'] == ['critical.new']
    assert cosmos.items[original.user_id]['user']['profile'] == original.profile.to_document()


def test_conditional_publication_rejects_stale_read_without_write():
    cosmos = Cosmos()
    store = CosmosUsersRuntimeStore(client=cosmos, container_name='users-runtime')
    initial = _user()
    store.upsert_user_if_current(initial, expected=None)
    desired = replace(initial, enabled=False)
    with pytest.raises(UsersIdentityConflictError, match='changed'):
        store.upsert_user_if_current(desired, expected=desired)
    assert cosmos.items[initial.user_id]['user']['enabled'] is True
