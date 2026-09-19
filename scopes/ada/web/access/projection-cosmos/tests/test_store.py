from datetime import UTC, datetime, timedelta

import pytest

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.models import ProfileAccessGrant
from ada.web.access.projection.cosmos import (
    ADA_ACCESS_PROJECTION_STORAGE_RESOURCE,
    CosmosAdaAccessProjectionStore,
    CosmosAdaAccessProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


class _CosmosClient:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, object], dict[str, object]] = {}
        self.fail_reads = False
        self.fail_writes = False

    def find_item(self, *, container_name, item_id, partition_key):
        if self.fail_reads:
            raise CosmosError('read failed')
        document = self.items.get((container_name, item_id, partition_key))
        return dict(document) if document is not None else None

    def upsert_item(self, *, container_name, item):
        if self.fail_writes:
            raise CosmosError('write failed')
        saved = dict(item)
        self.items[(container_name, str(saved['id']), saved['partition_key'])] = saved
        return saved


def _dependency(release_id: str = 'profiles-1') -> ProjectionTarget:
    return ProjectionTarget(
        source_key=SourceKey('profiles-configuration'),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(release_id),
            published_at_utc=datetime(2026, 9, 19, 10, tzinfo=UTC),
        ),
    )


def _record(
    *,
    source_key: str = 'ada-access',
    release_id: str = 'access-1',
    access_key: str = 'alarms.view',
    dependency_release: str = 'profiles-1',
    offset_seconds: int = 0,
) -> ProjectionRecord[AdaAccessConfiguration]:
    published_at = datetime(2026, 9, 19, 12, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return ProjectionRecord(
        source_key=SourceKey(source_key),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=published_at,
        projected_at_utc=published_at + timedelta(seconds=1),
        payload=AdaAccessConfiguration(
            profile_access=(
                ProfileAccessGrant(
                    profile_key='11111111-1111-4111-8111-111111111111',
                    access_keys=(access_key,),
                ),
            )
        ),
        dependencies=(_dependency(dependency_release),),
    )


def test_cosmos_projection_store_round_trips_exact_target_and_dependencies() -> None:
    store = CosmosAdaAccessProjectionStore(
        client=_CosmosClient(),
        settings=CosmosAdaAccessProjectionStoreSettings(container_name='ada-access-projection'),
    )
    record = _record()

    assert store.get_active(record.source_key) is None
    saved = store.replace_active(record)
    loaded = store.get_active(record.source_key)

    assert saved == record
    assert loaded == record
    assert loaded is not None
    assert loaded.target == record.target


def test_cosmos_projection_store_can_use_shared_users_support_container() -> None:
    client = _CosmosClient()
    store = CosmosAdaAccessProjectionStore(
        client=client,
        settings=CosmosAdaAccessProjectionStoreSettings(container_name='users-support'),
    )
    record = _record()

    store.replace_active(record)

    assert store.get_active(record.source_key) == record
    assert len(client.items) == 1


def test_cosmos_projection_store_separates_source_keys_and_replaces_same_key() -> None:
    client = _CosmosClient()
    store = CosmosAdaAccessProjectionStore(
        client=client,
        settings=CosmosAdaAccessProjectionStoreSettings(container_name='access'),
    )
    first = _record(source_key='access-a', release_id='a1')
    replacement = _record(
        source_key='access-a',
        release_id='a2',
        access_key='alarms.manage',
        dependency_release='profiles-2',
        offset_seconds=10,
    )
    second = _record(source_key='access-b', release_id='b1')

    store.replace_active(first)
    store.replace_active(second)
    store.replace_active(replacement)

    assert store.get_active(first.source_key) == replacement
    assert store.get_active(second.source_key) == second
    assert len(client.items) == 2


def test_cosmos_projection_store_wraps_connector_failures() -> None:
    client = _CosmosClient()
    store = CosmosAdaAccessProjectionStore(
        client=client,
        settings=CosmosAdaAccessProjectionStoreSettings(container_name='access'),
    )
    record = _record()
    client.fail_reads = True

    with pytest.raises(AdaAccessConfigurationProjectionError):
        store.get_active(record.source_key)

    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(AdaAccessConfigurationProjectionError):
        store.replace_active(record)


def test_cosmos_projection_store_requires_clean_container_name() -> None:
    with pytest.raises(ValueError):
        CosmosAdaAccessProjectionStoreSettings(container_name=' access ')


def test_cosmos_projection_storage_contract_is_access_owned_and_standalone() -> None:
    resource = ADA_ACCESS_PROJECTION_STORAGE_RESOURCE

    assert resource.logical_id == 'ada.access.projection'
    assert resource.owner == 'ada.access'
    assert resource.provider == 'cosmos'
    assert resource.default_physical_name == 'ada-access-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
