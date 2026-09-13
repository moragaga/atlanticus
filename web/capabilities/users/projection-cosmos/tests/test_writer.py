from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosOperationError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
    CosmosQueryParameter,
)
from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError
from atlanticus.web.users.configuration.models import UserConfiguration, UsersConfigurationCatalog
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.projection.cosmos import CosmosUsersRuntimeProjectionWriter


class FakeCosmosClient:
    def __init__(self, documents: Sequence[Mapping[str, Any]] = ()) -> None:
        self.documents = {str(item['id']): dict(item) for item in documents}
        self.find_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.patch_calls: list[dict[str, object]] = []
        self.iter_calls: list[dict[str, object]] = []
        self.create_conflict_document: dict[str, Any] | None = None
        self.patch_precondition_document: dict[str, Any] | None = None
        self.iter_error: Exception | None = None
        self.find_error: Exception | None = None
        self._etag_counter = 100

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None:
        self.find_calls.append(
            {
                'container_name': container_name,
                'item_id': item_id,
                'partition_key': partition_key,
                'include_metadata': include_metadata,
            }
        )
        if self.find_error is not None:
            raise self.find_error
        document = self.documents.get(item_id)
        return None if document is None else dict(document)

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                'container_name': container_name,
                'item': dict(item),
                'include_metadata': include_metadata,
            }
        )
        if self.create_conflict_document is not None:
            raced = dict(self.create_conflict_document)
            self.create_conflict_document = None
            self.documents[str(raced['id'])] = raced
            raise CosmosConflictError('exists')
        document = dict(item)
        document['_etag'] = self._next_etag()
        self.documents[str(document['id'])] = document
        return dict(document)

    def patch_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        operations: Sequence[CosmosPatchOperation],
        if_match_etag: str | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        self.patch_calls.append(
            {
                'container_name': container_name,
                'item_id': item_id,
                'partition_key': partition_key,
                'operations': tuple(operations),
                'if_match_etag': if_match_etag,
                'include_metadata': include_metadata,
            }
        )
        if self.patch_precondition_document is not None:
            raced = dict(self.patch_precondition_document)
            self.patch_precondition_document = None
            self.documents[item_id] = raced
            raise CosmosPreconditionFailedError('stale')
        document = dict(self.documents[item_id])
        for operation in operations:
            assert operation.operation == 'set'
            document[operation.path.removeprefix('/')] = operation.value
        document['_etag'] = self._next_etag()
        self.documents[item_id] = document
        return dict(document)

    def iter_items(
        self,
        *,
        container_name: str,
        query: str,
        parameters: Sequence[CosmosQueryParameter | Mapping[str, Any]] | None = None,
        cross_partition: bool = False,
        include_metadata: bool = False,
    ) -> Iterator[dict[str, Any]]:
        self.iter_calls.append(
            {
                'container_name': container_name,
                'query': query,
                'parameters': tuple(parameters or ()),
                'cross_partition': cross_partition,
                'include_metadata': include_metadata,
            }
        )
        if self.iter_error is not None:
            raise self.iter_error
        documents = tuple(dict(item) for item in self.documents.values())
        if 'record_type = @record_type' in query:
            documents = tuple(item for item in documents if item.get('record_type') == 'resolved')
        return iter(documents)

    def reset_calls(self) -> None:
        self.find_calls.clear()
        self.create_calls.clear()
        self.patch_calls.clear()
        self.iter_calls.clear()

    def _next_etag(self) -> str:
        self._etag_counter += 1
        return f'etag-{self._etag_counter}'


def _user(
    *,
    subject_id: str = 'oid-1',
    display_name: str = 'Managed User',
    email: str | None = 'managed@example.com',
    enabled: bool = True,
) -> UserConfiguration:
    return UserConfiguration.create(
        issuer='entra',
        subject_id=subject_id,
        display_name=display_name,
        email=email,
        profile_key='administrator',
        enabled=enabled,
    )


def _bundle(*users: UserConfiguration) -> UsersConfigurationBundle:
    return UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(users=tuple(users)),
        saved_by='source-admin',
        now_utc=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
    )


def _pending_document(*, subject_id: str = 'oid-1', etag: str = 'etag-pending') -> dict[str, Any]:
    return {
        'id': build_user_key(issuer='entra', subject_id=subject_id),
        'record_type': 'pending',
        'issuer': 'entra',
        'subject_id': subject_id,
        'display_name': 'Observed User',
        'email': 'observed@example.com',
        '_etag': etag,
    }


def _resolved_document(
    *,
    subject_id: str = 'oid-1',
    display_name: str = 'Managed User',
    email: str | None = 'managed@example.com',
    enabled: bool = True,
    profile_key: str = 'administrator',
    is_local: bool = False,
    managed_state: str | None = 'present',
    source_revision: str | None = 'old-revision',
    projected_at_utc: str | None = '2026-09-12T12:00:00+00:00',
    etag: str = 'etag-resolved',
) -> dict[str, Any]:
    document: dict[str, Any] = {
        'id': build_user_key(issuer='entra', subject_id=subject_id),
        'record_type': 'resolved',
        'issuer': 'entra',
        'subject_id': subject_id,
        'display_name': display_name,
        'email': email,
        'enabled': enabled,
        'profile_key': profile_key,
        'avatar_background_color': None,
        'avatar_text_color': None,
        'is_local': is_local,
        '_etag': etag,
    }
    if managed_state is not None:
        document['managed_state'] = managed_state
    if source_revision is not None:
        document['projection_source_revision'] = source_revision
    if projected_at_utc is not None:
        document['projected_at_utc'] = projected_at_utc
        document['projected_by'] = 'previous-admin'
    return document


def _writer(client: FakeCosmosClient) -> CosmosUsersRuntimeProjectionWriter:
    return CosmosUsersRuntimeProjectionWriter(client=client, container_name='users-runtime')


def test_materialize_creates_resolved_managed_record_for_configured_user() -> None:
    user = _user()
    bundle = _bundle(user)
    client = FakeCosmosClient()

    _writer(client).materialize(bundle, actor='configuration-admin')

    document = client.documents[user.user_id]
    assert document['record_type'] == 'resolved'
    assert document['issuer'] == user.issuer
    assert document['subject_id'] == user.subject_id
    assert document['display_name'] == user.display_name
    assert document['email'] == user.email
    assert document['enabled'] is True
    assert document['profile_key'] == 'administrator'
    assert document['avatar_background_color'] is None
    assert document['avatar_text_color'] is None
    assert document['is_local'] is False
    assert document['managed_state'] == 'present'
    assert document['projection_source_revision'] == bundle.revision
    assert document['projected_by'] == 'configuration-admin'
    assert datetime.fromisoformat(document['projected_at_utc']).tzinfo is not None
    assert len(client.create_calls) == 1
    assert client.patch_calls == []


def test_materialize_promotes_pending_record_in_place_with_etag() -> None:
    user = _user()
    client = FakeCosmosClient((_pending_document(),))

    _writer(client).materialize(_bundle(user), actor='configuration-admin')

    document = client.documents[user.user_id]
    assert document['record_type'] == 'resolved'
    assert document['managed_state'] == 'present'
    assert document['display_name'] == 'Managed User'
    assert len(client.patch_calls) == 1
    assert client.patch_calls[0]['if_match_etag'] == 'etag-pending'
    assert client.create_calls == []


def test_materialize_keeps_source_disabled_user_present_and_disabled() -> None:
    user = _user(enabled=False)
    client = FakeCosmosClient()

    _writer(client).materialize(_bundle(user), actor='configuration-admin')

    document = client.documents[user.user_id]
    assert document['managed_state'] == 'present'
    assert document['enabled'] is False


def test_materialize_retires_managed_user_removed_from_source() -> None:
    removed = _resolved_document(display_name='Removed User')
    user_id = str(removed['id'])
    client = FakeCosmosClient((removed,))
    bundle = _bundle()

    _writer(client).materialize(bundle, actor='configuration-admin')

    document = client.documents[user_id]
    assert document['record_type'] == 'resolved'
    assert document['managed_state'] == 'retired'
    assert document['enabled'] is False
    assert document['display_name'] == 'Removed User'
    assert document['profile_key'] == 'administrator'
    assert document['projection_source_revision'] == bundle.revision
    assert len(client.patch_calls) == 1


def test_materialize_does_not_retire_local_resolved_user() -> None:
    local = _resolved_document(
        profile_key='local',
        is_local=True,
        managed_state=None,
        source_revision=None,
        projected_at_utc=None,
    )
    user_id = str(local['id'])
    client = FakeCosmosClient((local,))

    _writer(client).materialize(_bundle(), actor='configuration-admin')

    assert client.documents[user_id] == local
    assert client.patch_calls == []


def test_materialize_readds_retired_user_with_current_source_values() -> None:
    user = _user(display_name='Current Name', email='current@example.com')
    retired = _resolved_document(
        display_name='Old Name',
        email='old@example.com',
        enabled=False,
        managed_state='retired',
    )
    client = FakeCosmosClient((retired,))

    _writer(client).materialize(_bundle(user), actor='configuration-admin')

    document = client.documents[user.user_id]
    assert document['managed_state'] == 'present'
    assert document['enabled'] is True
    assert document['display_name'] == 'Current Name'
    assert document['email'] == 'current@example.com'


def test_create_conflict_with_concurrent_pending_observation_is_promoted() -> None:
    user = _user()
    client = FakeCosmosClient()
    client.create_conflict_document = _pending_document()

    _writer(client).materialize(_bundle(user), actor='configuration-admin')

    assert client.documents[user.user_id]['record_type'] == 'resolved'
    assert len(client.create_calls) == 1
    assert len(client.patch_calls) == 1


def test_create_conflict_with_same_concurrent_projection_is_success() -> None:
    user = _user()
    bundle = _bundle(user)
    raced = _resolved_document(
        display_name=user.display_name,
        email=user.email,
        source_revision=bundle.revision,
        projected_at_utc=datetime.now(UTC).isoformat(),
    )
    raced['projected_by'] = 'other-worker'
    client = FakeCosmosClient()
    client.create_conflict_document = raced

    _writer(client).materialize(bundle, actor='configuration-admin')

    assert len(client.create_calls) == 1
    assert client.patch_calls == []


def test_create_conflict_with_different_resolved_state_fails() -> None:
    user = _user()
    client = FakeCosmosClient()
    client.create_conflict_document = _resolved_document(display_name='Concurrent Value')

    with pytest.raises(
        UsersConfigurationProjectionError,
        match='changed concurrently during projection create',
    ):
        _writer(client).materialize(_bundle(user), actor='configuration-admin')


def test_etag_conflict_accepts_concurrent_semantically_desired_state() -> None:
    user = _user()
    bundle = _bundle(user)
    client = FakeCosmosClient((_pending_document(),))
    concurrent = _resolved_document(
        display_name=user.display_name,
        email=user.email,
        source_revision=bundle.revision,
        projected_at_utc=datetime.now(UTC).isoformat(),
        etag='etag-concurrent',
    )
    concurrent['projected_by'] = 'other-worker'
    client.patch_precondition_document = concurrent

    _writer(client).materialize(bundle, actor='configuration-admin')

    assert client.documents[user.user_id]['projection_source_revision'] == bundle.revision
    assert len(client.patch_calls) == 1


def test_etag_conflict_rejects_concurrent_different_state() -> None:
    user = _user()
    client = FakeCosmosClient((_pending_document(),))
    client.patch_precondition_document = _resolved_document(
        display_name='Concurrent Different Value',
        etag='etag-concurrent',
    )

    with pytest.raises(
        UsersConfigurationProjectionError,
        match='changed concurrently during projection update',
    ):
        _writer(client).materialize(_bundle(user), actor='configuration-admin')


def test_materialize_rejects_corrupt_runtime_identity() -> None:
    corrupt = _resolved_document()
    corrupt['subject_id'] = 'other-subject'
    client = FakeCosmosClient((corrupt,))

    with pytest.raises(
        UsersConfigurationProjectionError,
        match='projection document is invalid',
    ):
        _writer(client).materialize(_bundle(), actor='configuration-admin')


def test_materialize_wraps_cosmos_failure_with_original_cause() -> None:
    source_error = CosmosOperationError('failed')
    client = FakeCosmosClient()
    client.iter_error = source_error

    with pytest.raises(UsersConfigurationProjectionError) as caught:
        _writer(client).materialize(_bundle(), actor='configuration-admin')

    assert caught.value.__cause__ is source_error


def test_replay_same_source_is_functionally_idempotent() -> None:
    user = _user()
    bundle = _bundle(user)
    client = FakeCosmosClient()
    writer = _writer(client)
    writer.materialize(bundle, actor='configuration-admin')
    client.reset_calls()

    writer.materialize(bundle, actor='configuration-admin')

    assert client.create_calls == []
    assert client.patch_calls == []


def test_materialize_rejects_newer_concurrent_projection() -> None:
    user = _user()
    future = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    concurrent = _resolved_document(
        display_name='Newer Value',
        source_revision='different-source-revision',
        projected_at_utc=future,
    )
    client = FakeCosmosClient((concurrent,))

    with pytest.raises(
        UsersConfigurationProjectionError,
        match='newer concurrent projection',
    ):
        _writer(client).materialize(_bundle(user), actor='configuration-admin')


def test_health_check_queries_bound_container_without_materializing_results() -> None:
    client = FakeCosmosClient()

    assert _writer(client).health_check() is True
    assert client.iter_calls == [
        {
            'container_name': 'users-runtime',
            'query': 'SELECT TOP 1 * FROM c',
            'parameters': (),
            'cross_partition': True,
            'include_metadata': False,
        }
    ]


def test_health_check_returns_false_for_cosmos_failure() -> None:
    client = FakeCosmosClient()
    client.iter_error = CosmosOperationError('failed')

    assert _writer(client).health_check() is False


@pytest.mark.parametrize('container_name', ['', ' users-runtime', 'users-runtime '])
def test_constructor_rejects_invalid_container_binding(container_name: str) -> None:
    with pytest.raises(UsersConfigurationProjectionError, match='container name'):
        CosmosUsersRuntimeProjectionWriter(client=FakeCosmosClient(), container_name=container_name)
