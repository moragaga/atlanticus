from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.projection.local import (
    LocalNavigationProjectionStore,
    LocalNavigationProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


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


def test_local_projection_store_round_trip_survives_restart(tmp_path) -> None:
    settings = LocalNavigationProjectionStoreSettings(root=tmp_path)
    record = _record()

    first = LocalNavigationProjectionStore(settings)
    assert first.get_active(record.source_key) is None
    assert first.replace_active(record) == record

    restarted = LocalNavigationProjectionStore(settings)
    assert restarted.get_active(record.source_key) == record


def test_local_projection_store_keeps_one_projection_per_source_key(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    first = _record(source_key='navigation-a', release_id='a1', label='A')
    second = _record(source_key='navigation-b', release_id='b1', label='B')

    store.replace_active(first)
    store.replace_active(second)

    assert store.get_active(first.source_key) == first
    assert store.get_active(second.source_key) == second


def test_local_projection_store_replaces_same_source_key(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    first = _record(release_id='release-1', label='First')
    second = _record(release_id='release-2', label='Second', offset_seconds=10)

    store.replace_active(first)
    store.replace_active(second)

    assert store.get_active(first.source_key) == second
    assert len(tuple(tmp_path.glob('navigation_projection_*.json'))) == 1


def test_local_projection_store_rejects_corrupt_projection(tmp_path) -> None:
    store = LocalNavigationProjectionStore(LocalNavigationProjectionStoreSettings(root=tmp_path))
    record = _record()
    store.replace_active(record)
    path = next(tmp_path.glob('navigation_projection_*.json'))
    path.write_text('{"document_type":"wrong"}', encoding='utf-8')

    with pytest.raises(NavigationConfigurationProjectionError):
        store.get_active(record.source_key)
