from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosItemNotFoundError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, GUEST_PROFILE_KEY
from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_JANE
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.models import RuntimeProfile

class MemoryCosmos:
    def __init__(self):
        self.items = {}
        self.revision = 0

    def _with_etag(self, document):
        result = dict(document)
        result['_etag'] = f'e{self.revision}'
        return result

    def find_item(
        self, *, container_name, item_id, partition_key, include_metadata=False,
    ):
        value = self.items.get(item_id)
        return None if value is None else dict(value)

    def create_item(self, *, container_name, item, include_metadata=False):
        item_id = item['id']
        if item_id in self.items:
            raise CosmosConflictError(item_id)
        self.revision += 1
        self.items[item_id] = self._with_etag(item)
        return dict(self.items[item_id])

    def patch_item(
        self, *, container_name, item_id, partition_key, operations,
        if_match_etag=None, include_metadata=False,
    ):
        if item_id not in self.items:
            raise CosmosItemNotFoundError(item_id)
        current = self.items[item_id]
        if if_match_etag is not None and current.get('_etag') != if_match_etag:
            raise CosmosConflictError(item_id)
        updated = dict(current)
        for operation in operations:
            assert operation.operation == 'set'
            updated[operation.path.removeprefix('/')] = operation.value
        self.revision += 1
        updated['_etag'] = f'e{self.revision}'
        self.items[item_id] = updated
        return dict(updated)

    def query_items(
        self, *, container_name, query, parameters=None,
        cross_partition=False, include_metadata=False,
    ):
        values = {item.name: item.value for item in parameters or ()}
        return tuple(
            dict(item) for item in self.items.values()
            if item.get('document_type') == values.get('@document_type')
        )

    def delete_item(
        self, *, container_name, item_id, partition_key, if_match_etag=None,
    ):
        if item_id not in self.items:
            raise CosmosItemNotFoundError(item_id)
        current = self.items[item_id]
        if if_match_etag is not None and current.get('_etag') != if_match_etag:
            raise CosmosConflictError(item_id)
        del self.items[item_id]


def _identity(subject='alice'):
    return AuthenticatedIdentity(
        provider_key='entra', issuer='tenant', subject_id=subject,
        display_name='Alice', email='alice@example.com',
    )


def test_observed_guest_is_durable_discoverable_and_idempotent():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    first = store.observe_guest(_identity())
    second = store.observe_guest(_identity())
    assert first == second == store.resolve(_identity())
    assert first.user_id == build_user_key(issuer='tenant', subject_id='alice')
    assert first.profile.id == GUEST_PROFILE_KEY
    assert first.access_keys == ()
    assert len(client.items) == 1
    assert tuple(guest.user_id for guest in store.list_guests()) == (first.user_id,)


def test_guest_observation_does_not_downgrade_promoted_user():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    guest = store.observe_guest(_identity())
    promoted = replace(guest, profile=RuntimeProfile.from_profile(BASIC_PROFILE))
    assert store.upsert_user_if_current(promoted, expected=guest) == promoted
    assert store.observe_guest(_identity()) == promoted
    assert store.list_guests() == ()


def test_guest_conflict_reads_winner_without_overwriting():
    class RacingCosmos(MemoryCosmos):
        def __init__(self):
            super().__init__()
            self.promoted = None

        def create_item(self, *, container_name, item, include_metadata=False):
            if self.promoted is None:
                return super().create_item(
                    container_name=container_name, item=item,
                    include_metadata=include_metadata,
                )
            self.items[item['id']] = dict(self.promoted)
            raise CosmosConflictError(item['id'])

    client = RacingCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    first = store.observe_guest(_identity())
    client.items.clear()
    client.promoted = {
        'id': first.user_id,
        'document_type': 'atlanticus_tool_runtime_user',
        'schema_version': 2,
        'user': replace(first, profile=RuntimeProfile.from_profile(BASIC_PROFILE)).to_document(),
    }
    winner = store.observe_guest(_identity())
    assert winner.profile.id == BASIC_PROFILE.key
    assert client.items[first.user_id]['user']['profile']['id'] == BASIC_PROFILE.key


def test_local_identity_is_not_observed_or_offered_for_promotion():
    client = MemoryCosmos()
    store = CosmosUsersRuntimeStore(client=client, container_name='users-runtime')
    identity = AuthenticatedIdentity(
        provider_key='local', issuer=LOCAL_ISSUER, subject_id=LOCAL_JANE.subject_id,
    )
    with pytest.raises(UsersDefinitionError, match='Local identities'):
        store.observe_guest(identity)
    assert client.items == {}

    guest = store.observe_guest(_identity())
    legacy_local_guest = replace(guest, identity=LOCAL_JANE.to_identity())
    assert store.upsert_user_if_current(legacy_local_guest, expected=None) == legacy_local_guest
    assert store.resolve(identity) == legacy_local_guest
    assert tuple(item.user_id for item in store.list_guests()) == (guest.user_id,)
    assert legacy_local_guest.user_id in client.items
