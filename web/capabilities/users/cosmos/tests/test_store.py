from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosOperationError,
    CosmosQueryParameter,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore
from atlanticus.web.users.errors import (
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersRuntimeStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord, ResolvedUserRecord


class FakeCosmosClient:
    def __init__(self) -> None:
        self.find_result: dict[str, Any] | None = None
        self.create_result: dict[str, Any] | None = None
        self.query_result: tuple[dict[str, Any], ...] = ()
        self.find_error: Exception | None = None
        self.create_error: Exception | None = None
        self.query_error: Exception | None = None
        self.find_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.query_calls: list[dict[str, object]] = []

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None:
        self.find_calls.append(
            {
                'container_name': container_name,
                'item_id': item_id,
                'partition_key': partition_key,
            }
        )
        if self.find_error is not None:
            raise self.find_error
        return self.find_result

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                'container_name': container_name,
                'item': dict(item),
            }
        )
        if self.create_error is not None:
            raise self.create_error
        if self.create_result is not None:
            return self.create_result
        return dict(item)

    def query_items(
        self,
        *,
        container_name: str,
        query: str,
        parameters: Sequence[CosmosQueryParameter | Mapping[str, Any]] | None = None,
        cross_partition: bool = False,
    ) -> tuple[dict[str, Any], ...]:
        self.query_calls.append(
            {
                'container_name': container_name,
                'query': query,
                'parameters': tuple(parameters or ()),
                'cross_partition': cross_partition,
            }
        )
        if self.query_error is not None:
            raise self.query_error
        return self.query_result


def _identity(
    *,
    issuer: str = 'entra',
    subject_id: str = 'oid-1',
) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer=issuer,
        subject_id=subject_id,
        display_name='Unknown User',
        email='Unknown@Example.com',
    )


def _user_id(*, issuer: str = 'entra', subject_id: str = 'oid-1') -> str:
    return build_user_key(issuer=issuer, subject_id=subject_id)


def _pending_document(
    *,
    issuer: str = 'entra',
    subject_id: str = 'oid-1',
) -> dict[str, object]:
    return {
        'id': _user_id(issuer=issuer, subject_id=subject_id),
        'record_type': 'pending',
        'issuer': issuer,
        'subject_id': subject_id,
        'display_name': 'Pending User',
        'email': 'pending@example.com',
    }


def _resolved_document(
    *,
    issuer: str = 'entra',
    subject_id: str = 'oid-1',
    enabled: bool = True,
) -> dict[str, object]:
    return {
        'id': _user_id(issuer=issuer, subject_id=subject_id),
        'record_type': 'resolved',
        'issuer': issuer,
        'subject_id': subject_id,
        'display_name': 'Managed User',
        'email': 'managed@example.com',
        'enabled': enabled,
        'profile_key': 'administrator',
        'avatar_background_color': None,
        'avatar_text_color': None,
        'is_local': False,
    }


def _store(client: FakeCosmosClient) -> CosmosUsersRuntimeStore:
    return CosmosUsersRuntimeStore(client=client, container_name='users-runtime')


def test_resolve_uses_deterministic_id_as_item_and_partition_key() -> None:
    client = FakeCosmosClient()
    client.find_result = _pending_document()

    result = _store(client).resolve(_identity())

    assert isinstance(result, PendingUserRecord)
    user_id = _user_id()
    assert client.find_calls == [
        {
            'container_name': 'users-runtime',
            'item_id': user_id,
            'partition_key': user_id,
        }
    ]


def test_resolve_returns_none_only_when_item_is_absent() -> None:
    client = FakeCosmosClient()

    assert _store(client).resolve(_identity()) is None


def test_resolve_decodes_resolved_user() -> None:
    client = FakeCosmosClient()
    client.find_result = _resolved_document(enabled=False)

    result = _store(client).resolve(_identity())

    assert isinstance(result, ResolvedUserRecord)
    assert result.enabled is False
    assert result.profile_key == 'administrator'


def test_resolve_rejects_document_identity_that_does_not_match_id() -> None:
    client = FakeCosmosClient()
    document = _pending_document()
    document['subject_id'] = 'oid-2'
    client.find_result = document

    with pytest.raises(UsersIdentityConflictError):
        _store(client).resolve(_identity())


def test_resolve_rejects_unknown_record_type() -> None:
    client = FakeCosmosClient()
    document = _pending_document()
    document['record_type'] = 'other'
    client.find_result = document

    with pytest.raises(UsersDefinitionError, match='Unsupported users Cosmos record type'):
        _store(client).resolve(_identity())


def test_resolve_wraps_cosmos_failure_as_store_unavailable() -> None:
    client = FakeCosmosClient()
    source_error = CosmosOperationError('failed')
    client.find_error = source_error

    with pytest.raises(UsersRuntimeStoreUnavailableError) as caught:
        _store(client).resolve(_identity())

    assert caught.value.__cause__ is source_error


def test_observe_creates_pending_record_without_upsert() -> None:
    client = FakeCosmosClient()

    result = _store(client).observe(_identity())

    assert isinstance(result, PendingUserRecord)
    assert result.email == 'unknown@example.com'
    assert len(client.create_calls) == 1
    body = client.create_calls[0]['item']
    assert isinstance(body, dict)
    assert body == {
        'id': _user_id(),
        'record_type': 'pending',
        'issuer': 'entra',
        'subject_id': 'oid-1',
        'display_name': 'Unknown User',
        'email': 'Unknown@Example.com',
    }


def test_observe_conflict_rereads_existing_pending_record() -> None:
    client = FakeCosmosClient()
    client.create_error = CosmosConflictError('exists')
    client.find_result = _pending_document()

    result = _store(client).observe(_identity())

    assert isinstance(result, PendingUserRecord)
    assert len(client.create_calls) == 1
    assert len(client.find_calls) == 1


def test_observe_conflict_returns_concurrently_promoted_user() -> None:
    client = FakeCosmosClient()
    client.create_error = CosmosConflictError('exists')
    client.find_result = _resolved_document(enabled=True)

    result = _store(client).observe(_identity())

    assert isinstance(result, ResolvedUserRecord)
    assert result.enabled is True


def test_observe_conflict_returns_concurrently_disabled_user() -> None:
    client = FakeCosmosClient()
    client.create_error = CosmosConflictError('exists')
    client.find_result = _resolved_document(enabled=False)

    result = _store(client).observe(_identity())

    assert isinstance(result, ResolvedUserRecord)
    assert result.enabled is False


def test_observe_conflict_fails_if_record_disappears_before_reread() -> None:
    client = FakeCosmosClient()
    client.create_error = CosmosConflictError('exists')

    with pytest.raises(
        UsersRuntimeStoreUnavailableError,
        match='disappeared after observation conflict',
    ):
        _store(client).observe(_identity())


def test_observe_wraps_non_conflict_cosmos_failure() -> None:
    client = FakeCosmosClient()
    source_error = CosmosOperationError('failed')
    client.create_error = source_error

    with pytest.raises(UsersRuntimeStoreUnavailableError) as caught:
        _store(client).observe(_identity())

    assert caught.value.__cause__ is source_error


def test_list_pending_queries_cross_partition_and_sorts_by_user_id() -> None:
    client = FakeCosmosClient()
    first = _pending_document(subject_id='oid-2')
    second = _pending_document(subject_id='oid-1')
    client.query_result = (first, second)

    result = _store(client).list_pending()

    assert tuple(record.user_id for record in result) == tuple(
        sorted((_user_id(subject_id='oid-2'), _user_id(subject_id='oid-1')))
    )
    assert len(client.query_calls) == 1
    call = client.query_calls[0]
    assert call['container_name'] == 'users-runtime'
    assert call['query'] == 'SELECT * FROM c WHERE c.record_type = @record_type'
    assert call['cross_partition'] is True
    parameters = call['parameters']
    assert isinstance(parameters, tuple)
    assert parameters == (CosmosQueryParameter(name='@record_type', value='pending'),)


def test_list_pending_rejects_non_pending_query_result() -> None:
    client = FakeCosmosClient()
    client.query_result = (_resolved_document(),)

    with pytest.raises(UsersDefinitionError, match='non-pending record'):
        _store(client).list_pending()


def test_list_pending_wraps_cosmos_failure() -> None:
    client = FakeCosmosClient()
    source_error = CosmosOperationError('failed')
    client.query_error = source_error

    with pytest.raises(UsersRuntimeStoreUnavailableError) as caught:
        _store(client).list_pending()

    assert caught.value.__cause__ is source_error


@pytest.mark.parametrize('container_name', ['', ' users-runtime', 'users-runtime '])
def test_constructor_rejects_invalid_container_binding(container_name: str) -> None:
    with pytest.raises(UsersDefinitionError, match='container name has an invalid format'):
        CosmosUsersRuntimeStore(client=FakeCosmosClient(), container_name=container_name)


def test_public_store_implements_both_users_contracts() -> None:
    from atlanticus.web.users.store import PendingUsersReader, UsersRuntimeStore

    store = _store(FakeCosmosClient())

    assert isinstance(store, UsersRuntimeStore)
    assert isinstance(store, PendingUsersReader)
