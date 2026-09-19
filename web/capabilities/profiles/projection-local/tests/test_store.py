from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.profiles.projection.local import (
    LocalProfilesProjectionStore,
    LocalProfilesProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


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


def test_local_projection_store_round_trip_survives_restart(tmp_path) -> None:
    settings = LocalProfilesProjectionStoreSettings(root=tmp_path)
    record = _record()

    first = LocalProfilesProjectionStore(settings)
    assert first.get_active(record.source_key) is None
    assert first.replace_active(record) is record

    restarted = LocalProfilesProjectionStore(settings)
    _assert_same_projection(restarted.get_active(record.source_key), record)


def test_local_projection_store_replaces_same_source_key(tmp_path) -> None:
    store = LocalProfilesProjectionStore(LocalProfilesProjectionStoreSettings(root=tmp_path))
    first = _record(release_id='release-1', label='Analista')
    second = _record(release_id='release-2', label='Analista Senior', offset_seconds=10)

    store.replace_active(first)
    store.replace_active(second)

    _assert_same_projection(store.get_active(first.source_key), second)
    assert len(tuple(tmp_path.glob('profiles_projection_*.json'))) == 1


def test_local_projection_store_separates_source_keys(tmp_path) -> None:
    store = LocalProfilesProjectionStore(LocalProfilesProjectionStoreSettings(root=tmp_path))
    first = _record(source_key='profiles-a', release_id='a1')
    second = _record(source_key='profiles-b', release_id='b1')

    store.replace_active(first)
    store.replace_active(second)

    _assert_same_projection(store.get_active(first.source_key), first)
    _assert_same_projection(store.get_active(second.source_key), second)


def test_local_projection_store_rejects_corrupt_projection(tmp_path) -> None:
    store = LocalProfilesProjectionStore(LocalProfilesProjectionStoreSettings(root=tmp_path))
    record = _record()
    store.replace_active(record)
    path = next(tmp_path.glob('profiles_projection_*.json'))
    path.write_text('{"document_type":"wrong"}', encoding='utf-8')

    with pytest.raises(ProfilesConfigurationProjectionError):
        store.get_active(record.source_key)
