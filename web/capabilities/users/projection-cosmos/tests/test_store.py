from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
)
from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionConflictError,
    UsersConfigurationProjectionError,
)
from atlanticus.web.users.projection.cosmos.store import (
    USERS_PROJECTION_DOCUMENT_TYPE,
    USERS_PROJECTION_SCHEMA_VERSION,
    CosmosUsersConfigurationProjectionStore,
)


@dataclass(slots=True)
class _Client:
    document: dict[str, Any] | None = None
    create_calls: int = 0
    patch_calls: int = 0
    concurrent_patch_document: dict[str, Any] | None = None

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ):
        assert container_name == 'users-projections'
        if self.document is None:
            return None
        assert self.document['id'] == item_id
        assert self.document['partition_key'] == partition_key
        result = deepcopy(self.document)
        if not include_metadata:
            result.pop('_etag', None)
        return result

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
        include_metadata: bool = False,
    ):
        assert container_name == 'users-projections'
        self.create_calls += 1
        if self.document is not None:
            raise CosmosConflictError('conflict')
        self.document = dict(item)
        self.document['_etag'] = 'etag-1'
        return self.find_item(
            container_name=container_name,
            item_id=self.document['id'],
            partition_key=self.document['partition_key'],
            include_metadata=include_metadata,
        )

    def patch_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        operations: Sequence[CosmosPatchOperation],
        if_match_etag: str | None = None,
        include_metadata: bool = False,
    ):
        assert self.document is not None
        self.patch_calls += 1
        if self.concurrent_patch_document is not None:
            self.document = deepcopy(self.concurrent_patch_document)
            self.document['_etag'] = 'etag-concurrent'
            self.concurrent_patch_document = None
            raise CosmosPreconditionFailedError('stale')
        if if_match_etag != self.document['_etag']:
            raise CosmosPreconditionFailedError('stale')
        for op in operations:
            self.document[op.path.removeprefix('/')] = deepcopy(op.value)
        self.document['_etag'] = f'etag-{self.patch_calls + 1}'
        return self.find_item(
            container_name=container_name,
            item_id=item_id,
            partition_key=partition_key,
            include_metadata=include_metadata,
        )


def _payload(color: str = '#0F6CBD') -> UsersProfilesConfiguration:
    return UsersProfilesConfiguration(
        users=UsersConfiguration(),
        profiles=ProfilesConfiguration(
            profiles=(
                ProfileDefinition('administrator', 'Administrador', color, '#FFFFFF'),
            )
        ),
    )


def _record(
    release_id: str,
    *,
    published_offset: int,
    projected_offset: int,
    color: str = '#0F6CBD',
):
    base = datetime(2026, 9, 13, 12, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('users-configuration'),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=base + timedelta(minutes=published_offset),
        projected_at_utc=base + timedelta(minutes=projected_offset),
        payload=_payload(color),
    )


def _id(source_key: SourceKey) -> str:
    return 'users-configuration-projection-' + hashlib.sha256(
        source_key.value.encode()
    ).hexdigest()


def _v2_document(record: ProjectionRecord[UsersProfilesConfiguration]) -> dict[str, Any]:
    return {
        'id': _id(record.source_key),
        'partition_key': record.source_key.value,
        'document_type': USERS_PROJECTION_DOCUMENT_TYPE,
        'schema_version': USERS_PROJECTION_SCHEMA_VERSION,
        'source_key': record.source_key.value,
        'source_release_id': record.source_release_id.value,
        'source_published_at_utc': record.source_published_at_utc.isoformat(),
        'projected_at_utc': record.projected_at_utc.isoformat(),
        'payload': record.payload.to_document(),
    }


def _store(client: _Client):
    return CosmosUsersConfigurationProjectionStore(
        client=client,
        container_name='users-projections',
    )


def test_new_projection_writes_schema_2_only() -> None:
    client = _Client()
    record = _record('release-1', published_offset=0, projected_offset=1)
    saved = _store(client).replace_active(record)
    assert saved == record
    assert client.document is not None
    assert client.document['schema_version'] == 2
    assert set(client.document['payload']) == {'users', 'profiles'}


def test_projection_rejects_non_current_schema_version() -> None:
    record = _record('release-1', published_offset=0, projected_offset=1)
    document = _v2_document(record)
    document['schema_version'] = 1
    client = _Client(document=document)
    client.document['_etag'] = 'etag-1'

    with pytest.raises(UsersConfigurationProjectionError, match='schema version is invalid'):
        _store(client).get_active(record.source_key)


def test_same_exact_release_with_different_payload_is_invariant_error() -> None:
    client = _Client()
    store = _store(client)
    store.replace_active(_record('release-1', published_offset=0, projected_offset=1))
    with pytest.raises(UsersConfigurationProjectionError, match='different payload'):
        store.replace_active(
            _record(
                'release-1',
                published_offset=0,
                projected_offset=2,
                color='#123456',
            )
        )
    assert client.patch_calls == 0


def test_new_release_replaces_active_with_cas_and_schema_2() -> None:
    client = _Client()
    store = _store(client)
    store.replace_active(_record('release-1', published_offset=0, projected_offset=1))
    second = _record('release-2', published_offset=2, projected_offset=3)
    assert store.replace_active(second) == second
    assert client.patch_calls == 1
    assert client.document['schema_version'] == 2


def test_concurrent_winner_different_target_raises_conflict() -> None:
    client = _Client()
    store = _store(client)
    first = _record('release-1', published_offset=0, projected_offset=1)
    candidate = _record('release-2', published_offset=2, projected_offset=3)
    concurrent = _record('release-3', published_offset=4, projected_offset=5)
    store.replace_active(first)
    client.concurrent_patch_document = _v2_document(concurrent)
    with pytest.raises(UsersConfigurationProjectionConflictError):
        store.replace_active(candidate)


def test_same_exact_release_and_payload_is_idempotent_and_preserves_projected_at() -> None:
    client = _Client()
    store = _store(client)
    first = _record('release-1', published_offset=0, projected_offset=1)
    retry = _record('release-1', published_offset=0, projected_offset=10)
    store.replace_active(first)

    saved = store.replace_active(retry)

    assert saved == first
    assert saved.projected_at_utc == first.projected_at_utc
    assert client.patch_calls == 0


def test_concurrent_winner_same_target_is_idempotent_success() -> None:
    client = _Client()
    store = _store(client)
    first = _record('release-1', published_offset=0, projected_offset=1)
    candidate = _record('release-2', published_offset=2, projected_offset=3)
    concurrent = _record('release-2', published_offset=2, projected_offset=4)
    store.replace_active(first)
    client.concurrent_patch_document = _v2_document(concurrent)

    saved = store.replace_active(candidate)

    assert saved == concurrent
    assert saved.projected_at_utc == concurrent.projected_at_utc


def test_sequential_projection_can_explicitly_activate_older_exact_release() -> None:
    client = _Client()
    store = _store(client)
    newer = _record('release-2', published_offset=2, projected_offset=3)
    older = _record('release-1', published_offset=0, projected_offset=4)
    store.replace_active(newer)

    saved = store.replace_active(older)

    assert saved == older
    assert store.get_active(older.source_key) == older
    assert client.patch_calls == 1
