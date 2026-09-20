from datetime import UTC, datetime, timedelta

import pytest

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.models import ProfileAccessGrant
from ada.web.access.projection.local import (
    LocalAdaAccessProjectionStore,
    LocalAdaAccessProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


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
            access_keys=(access_key,),
            profile_access=(
                ProfileAccessGrant(
                    profile_key='11111111-1111-4111-8111-111111111111',
                    access_keys=(access_key,),
                ),
            ),
        ),
        dependencies=(_dependency(dependency_release),),
    )


def test_local_projection_store_round_trip_survives_restart_with_dependencies(tmp_path) -> None:
    settings = LocalAdaAccessProjectionStoreSettings(root=tmp_path)
    record = _record()

    first = LocalAdaAccessProjectionStore(settings)
    assert first.get_active(record.source_key) is None
    assert first.replace_active(record) is record

    restarted = LocalAdaAccessProjectionStore(settings)
    assert restarted.get_active(record.source_key) == record


def test_local_projection_store_replaces_same_source_key(tmp_path) -> None:
    store = LocalAdaAccessProjectionStore(LocalAdaAccessProjectionStoreSettings(root=tmp_path))
    first = _record()
    second = _record(
        release_id='access-2',
        access_key='alarms.manage',
        dependency_release='profiles-2',
        offset_seconds=10,
    )

    store.replace_active(first)
    store.replace_active(second)

    assert store.get_active(first.source_key) == second
    assert len(tuple(tmp_path.glob('ada_access_projection_*.json'))) == 1


def test_local_projection_store_separates_source_keys(tmp_path) -> None:
    store = LocalAdaAccessProjectionStore(LocalAdaAccessProjectionStoreSettings(root=tmp_path))
    first = _record(source_key='access-a', release_id='a1')
    second = _record(source_key='access-b', release_id='b1')

    store.replace_active(first)
    store.replace_active(second)

    assert store.get_active(first.source_key) == first
    assert store.get_active(second.source_key) == second


def test_local_projection_store_rejects_corrupt_projection(tmp_path) -> None:
    store = LocalAdaAccessProjectionStore(LocalAdaAccessProjectionStoreSettings(root=tmp_path))
    record = _record()
    store.replace_active(record)
    path = next(tmp_path.glob('ada_access_projection_*.json'))
    path.write_text('{"document_type":"wrong"}', encoding='utf-8')

    with pytest.raises(AdaAccessConfigurationProjectionError):
        store.get_active(record.source_key)
