from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.profiles.projection.cosmos import (
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    CosmosProfilesProjectionStore,
    CosmosProfilesProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


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


def _record(
    *,
    source_key: str = 'profiles-configuration',
    release_id: str = 'release-1',
    label: str = 'Analista',
    offset_seconds: int = 0,
) -> ProjectionRecord[ProfileCatalog]:
    published_at = datetime(2026, 9, 19, 12, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return ProjectionRecord(
        source_key=SourceKey(source_key),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=published_at,
        projected_at_utc=published_at + timedelta(seconds=1),
        payload=ProfileCatalog(
            profiles=(
                ProfileDefinition(
                    key='11111111-1111-4111-8111-111111111111',
                    label=label,
                    background_color='#123456',
                ),
            )
        ),
    )


def _assert_same_projection(
    actual: ProjectionRecord[ProfileCatalog] | None,
    expected: ProjectionRecord[ProfileCatalog],
) -> None:
    assert actual is not None
    assert actual.source_key == expected.source_key
    assert actual.source_release == expected.source_release
    assert actual.projected_at_utc == expected.projected_at_utc
    assert actual.payload.all() == expected.payload.all()


def test_cosmos_projection_store_round_trips_exact_provenance() -> None:
    store = CosmosProfilesProjectionStore(
        client=_CosmosClient(),
        settings=CosmosProfilesProjectionStoreSettings(container_name='profiles'),
    )
    record = _record()

    assert store.get_active(record.source_key) is None
    saved = store.replace_active(record)
    loaded = store.get_active(record.source_key)

    _assert_same_projection(saved, record)
    _assert_same_projection(loaded, record)


def test_cosmos_projection_store_separates_source_keys_and_replaces_same_key() -> None:
    client = _CosmosClient()
    store = CosmosProfilesProjectionStore(
        client=client,
        settings=CosmosProfilesProjectionStoreSettings(container_name='profiles'),
    )
    first = _record(source_key='profiles-a', release_id='a1')
    replacement = _record(
        source_key='profiles-a',
        release_id='a2',
        label='Analista Senior',
        offset_seconds=10,
    )
    second = _record(source_key='profiles-b', release_id='b1')

    store.replace_active(first)
    store.replace_active(second)
    store.replace_active(replacement)

    _assert_same_projection(store.get_active(first.source_key), replacement)
    _assert_same_projection(store.get_active(second.source_key), second)
    assert len(client.items) == 2


def test_cosmos_projection_store_wraps_connector_failures() -> None:
    client = _CosmosClient()
    store = CosmosProfilesProjectionStore(
        client=client,
        settings=CosmosProfilesProjectionStoreSettings(container_name='profiles'),
    )
    record = _record()
    client.fail_reads = True

    with pytest.raises(ProfilesConfigurationProjectionError):
        store.get_active(record.source_key)

    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(ProfilesConfigurationProjectionError):
        store.replace_active(record)


def test_cosmos_projection_store_requires_clean_container_name() -> None:
    with pytest.raises(ValueError):
        CosmosProfilesProjectionStoreSettings(container_name=' profiles ')


def test_cosmos_projection_storage_contract_is_profiles_owned() -> None:
    resource = PROFILES_PROJECTION_STORAGE_RESOURCE

    assert resource.logical_id == 'profiles.projection'
    assert resource.owner == 'profiles'
    assert resource.provider == 'cosmos'
    assert resource.default_physical_name == 'profiles-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
