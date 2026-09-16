from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.projection.cosmos import (
    CosmosNavigationProjectionStore,
    CosmosNavigationProjectionStoreSettings,
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
    source_key: str = 'navigation-configuration',
    release_id: str = 'release-1',
    label: str = 'Home',
    offset_seconds: int = 0,
) -> ProjectionRecord[NavigationConfigurationCatalog]:
    published_at = datetime(2026, 9, 15, 12, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return ProjectionRecord(
        source_key=SourceKey(source_key),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=published_at,
        projected_at_utc=published_at + timedelta(seconds=1),
        payload=NavigationConfigurationCatalog(
            links=(NavigationLinkConfiguration(key='home', label=label, href='/'),)
        ),
    )


def test_cosmos_projection_store_round_trips_exact_provenance() -> None:
    store = CosmosNavigationProjectionStore(
        client=_CosmosClient(),
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    record = _record()

    assert store.get_active(record.source_key) is None
    saved = store.replace_active(record)
    loaded = store.get_active(record.source_key)

    assert saved == record
    assert loaded == record
    assert loaded is not None
    assert loaded.source_release == record.source_release


def test_cosmos_projection_store_separates_source_keys_and_replaces_same_key() -> None:
    client = _CosmosClient()
    store = CosmosNavigationProjectionStore(
        client=client,
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    first = _record(source_key='navigation-a', release_id='a1', label='A')
    replacement = _record(
        source_key='navigation-a', release_id='a2', label='A2', offset_seconds=10
    )
    second = _record(source_key='navigation-b', release_id='b1', label='B')

    store.replace_active(first)
    store.replace_active(second)
    store.replace_active(replacement)

    assert store.get_active(first.source_key) == replacement
    assert store.get_active(second.source_key) == second
    assert len(client.items) == 2


def test_cosmos_projection_store_wraps_connector_failures() -> None:
    client = _CosmosClient()
    store = CosmosNavigationProjectionStore(
        client=client,
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    record = _record()
    client.fail_reads = True

    with pytest.raises(NavigationConfigurationProjectionError):
        store.get_active(record.source_key)

    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(NavigationConfigurationProjectionError):
        store.replace_active(record)


def test_cosmos_projection_store_requires_clean_container_name() -> None:
    with pytest.raises(ValueError):
        CosmosNavigationProjectionStoreSettings(container_name=' configuration ')
