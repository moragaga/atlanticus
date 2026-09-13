from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.adapters import (
    CosmosNavigationProjectionStore,
    CosmosNavigationProjectionStoreSettings,
    LocalNavigationProjectionStore,
    LocalNavigationProjectionStoreSettings,
)
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _catalog(label: str) -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(NavigationLinkConfiguration(key='home', label=label, href='/'),),
    )


def _projection(
    *,
    source_key: str = 'navigation-configuration',
    release_id: str = 'release-1',
    label: str = 'Home',
    offset_seconds: int = 0,
) -> ProjectionRecord[NavigationConfigurationCatalog]:
    published_at = datetime(2026, 9, 13, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return ProjectionRecord(
        source_key=SourceKey(source_key),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=published_at,
        projected_at_utc=published_at + timedelta(seconds=1),
        payload=_catalog(label),
    )


class _FakeCosmosClient:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str, object], dict[str, Any]] = {}
        self.fail_reads = False
        self.fail_writes = False

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None:
        if self.fail_reads:
            raise RuntimeError('read failed')
        document = self.documents.get((container_name, item_id, partition_key))
        return dict(document) if document is not None else None

    def upsert_item(
        self,
        *,
        container_name: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        if self.fail_writes:
            raise RuntimeError('write failed')
        key = (container_name, str(item['id']), item['partition_key'])
        self.documents[key] = dict(item)
        return dict(item)


def test_local_projection_store_round_trip_survives_restart(tmp_path) -> None:
    settings = LocalNavigationProjectionStoreSettings(root=tmp_path)
    projection = _projection()

    first = LocalNavigationProjectionStore(settings)
    assert first.get_active(projection.source_key) is None
    assert first.replace_active(projection) == projection

    restarted = LocalNavigationProjectionStore(settings)
    assert restarted.get_active(projection.source_key) == projection


def test_local_projection_store_keeps_one_active_projection_per_source_key(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    first_key = _projection(source_key='navigation-a', release_id='a1', label='A')
    second_key = _projection(source_key='navigation-b', release_id='b1', label='B')

    store.replace_active(first_key)
    store.replace_active(second_key)

    assert store.get_active(first_key.source_key) == first_key
    assert store.get_active(second_key.source_key) == second_key


def test_local_projection_store_replaces_only_the_same_source_key(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    first = _projection(release_id='release-1', label='First')
    second = _projection(release_id='release-2', label='Second', offset_seconds=10)

    store.replace_active(first)
    store.replace_active(second)

    assert store.get_active(first.source_key) == second
    assert len(tuple(tmp_path.glob('navigation_projection_*.json'))) == 1


def test_local_projection_store_rejects_corrupt_persisted_state(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    projection = _projection()
    store.replace_active(projection)
    path = next(tmp_path.glob('navigation_projection_*.json'))
    path.write_text('{"document_type":"wrong"}', encoding='utf-8')

    with pytest.raises(NavigationConfigurationProjectionError):
        store.get_active(projection.source_key)


def test_cosmos_projection_store_round_trips_exact_provenance() -> None:
    client = _FakeCosmosClient()
    store = CosmosNavigationProjectionStore(
        client=client,
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    projection = _projection()

    assert store.get_active(projection.source_key) is None
    saved = store.replace_active(projection)
    loaded = store.get_active(projection.source_key)

    assert saved == projection
    assert loaded == projection
    assert loaded is not None
    assert loaded.source_release == projection.source_release


def test_cosmos_projection_store_separates_source_keys_and_replaces_same_key() -> None:
    client = _FakeCosmosClient()
    store = CosmosNavigationProjectionStore(
        client=client,
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    first = _projection(source_key='navigation-a', release_id='a1', label='A')
    replacement = _projection(
        source_key='navigation-a',
        release_id='a2',
        label='A2',
        offset_seconds=10,
    )
    second = _projection(source_key='navigation-b', release_id='b1', label='B')

    store.replace_active(first)
    store.replace_active(second)
    store.replace_active(replacement)

    assert store.get_active(first.source_key) == replacement
    assert store.get_active(second.source_key) == second
    assert len(client.documents) == 2


def test_cosmos_projection_store_wraps_client_failures() -> None:
    client = _FakeCosmosClient()
    store = CosmosNavigationProjectionStore(
        client=client,
        settings=CosmosNavigationProjectionStoreSettings(container_name='configuration'),
    )
    projection = _projection()
    client.fail_reads = True

    with pytest.raises(NavigationConfigurationProjectionError):
        store.get_active(projection.source_key)

    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(NavigationConfigurationProjectionError):
        store.replace_active(projection)
