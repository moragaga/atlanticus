from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosPatchOperation
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY, ROOT_AUTHORITY_KEY
from atlanticus.web.users.cosmos import CosmosUsersStore
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord


def user(subject: str) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra', subject_id=subject, display_name=f'User {subject}',
        email=None, enabled=True, authority_key=BASIC_AUTHORITY_KEY,
    )


class FakeCosmos:
    def __init__(self):
        self.items = {}
        self.query_result = None
        self.etag_sequence = 0

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        value = self.items.get(item_id)
        if value is None:
            return None
        result = dict(value)
        if include_metadata:
            result['_etag'] = result.get('_etag', 'etag')
        else:
            result.pop('_etag', None)
        return result

    def create_item(self, *, container_name, item, include_metadata=False):
        if item['id'] in self.items:
            raise CosmosConflictError
        self.etag_sequence += 1
        value = dict(item)
        value['_etag'] = f'e{self.etag_sequence}'
        self.items[item['id']] = value
        result = dict(value)
        if not include_metadata:
            result.pop('_etag', None)
        return result

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag=None, include_metadata=False):
        current = self.items[item_id]
        if current['_etag'] != if_match_etag:
            raise AssertionError('unexpected etag')
        for operation in operations:
            assert isinstance(operation, CosmosPatchOperation)
            current[operation.path[1:]] = operation.value
        self.etag_sequence += 1
        current['_etag'] = f'e{self.etag_sequence}'
        result = dict(current)
        if not include_metadata:
            result.pop('_etag', None)
        return result

    def query_items(self, *, container_name, query, parameters=None, cross_partition=False):
        return tuple({k: v for k, v in value.items() if k != '_etag'} for value in self.items.values())


def test_cosmos_store_contains_only_promoted_user_contract():
    client = FakeCosmos()
    store = CosmosUsersStore(client=client, container_name='users-runtime')
    managed = user('1')
    assert store.get(managed.user_id) is None
    assert store.create(managed) == managed
    identity = AuthenticatedIdentity(provider_key='entra', issuer='entra', subject_id='1')
    assert store.resolve(identity) == managed
    assert store.list_users() == (managed,)
    updated = replace(managed, enabled=False, authority_key=ROOT_AUTHORITY_KEY)
    assert store.replace(updated) == updated
    assert store.resolve(identity) == updated


def test_cosmos_store_rejects_old_pending_or_resolved_document_schema():
    client = FakeCosmos()
    managed = user('1')
    client.items[managed.user_id] = {
        'id': managed.user_id,
        'record_type': 'resolved',
        'issuer': managed.issuer,
        'subject_id': managed.subject_id,
        'display_name': managed.display_name,
        'email': managed.email,
        'enabled': True,
        'authority_key': 'basic',
        '_etag': 'e1',
    }
    store = CosmosUsersStore(client=client, container_name='users-runtime')
    with pytest.raises(UsersDefinitionError, match='document type'):
        store.get(managed.user_id)
