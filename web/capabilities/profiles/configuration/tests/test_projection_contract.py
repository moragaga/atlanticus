from datetime import UTC, datetime

import pytest

from atlanticus.web.profiles.configuration import (
    ProfilesConfiguration,
    ProfilesConfigurationProjectionError,
    ProfilesProjectionBuilder,
    ProfilesSourceCodec,
    profiles_projection_from_document,
    profiles_projection_to_document,
)
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import (
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceResourceMetadata,
)


def _configured_profile() -> ProfileDefinition:
    return ProfileDefinition(
        key='11111111-1111-4111-8111-111111111111',
        label='Analista',
        background_color='#123456',
        text_color='#ABCDEF',
    )


def _projection_record() -> ProjectionRecord[ProfileCatalog]:
    published_at = datetime(2026, 9, 19, 12, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('profiles-configuration'),
        source_release_id=SourceReleaseId('release-1'),
        source_published_at_utc=published_at,
        projected_at_utc=datetime(2026, 9, 19, 12, 0, 1, tzinfo=UTC),
        payload=ProfileCatalog(profiles=(_configured_profile(),)),
    )


def test_projection_builder_materializes_effective_profile_catalog() -> None:
    codec = ProfilesSourceCodec()
    resource = codec.encode(
        configuration=ProfilesConfiguration(profiles=(_configured_profile(),)),
        published_by='root',
    )
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId('release-1'),
        published_at_utc=datetime(2026, 9, 19, 12, tzinfo=UTC),
    )
    release = SourceReleaseMetadata(
        schema_version=1,
        source_key=SourceKey('profiles-configuration'),
        release_ref=release_ref,
        content_hash=Digest('sha256', 'content'),
        resources=(
            SourceResourceMetadata(
                logical_path=resource.logical_path,
                byte_length=len(resource.content),
                digest=Digest('sha256', 'resource'),
            ),
        ),
    )

    catalog = ProfilesProjectionBuilder().build(
        target=ProjectionTarget(
            source_key=release.source_key,
            source_release=release.release_ref,
        ),
        release=release,
        resources=(resource,),
    )

    assert tuple(profile.key for profile in catalog.all()) == (
        'basic',
        'root',
        'guest',
        'local',
        '11111111-1111-4111-8111-111111111111',
    )
    assert catalog.require('11111111-1111-4111-8111-111111111111').label == 'Analista'


def test_projection_record_round_trip_rebuilds_system_profiles_from_code() -> None:
    record = _projection_record()

    document = profiles_projection_to_document(record)
    restored = profiles_projection_from_document(document)

    payload = document['payload']
    assert isinstance(payload, dict)
    assert [item['key'] for item in payload['profiles']] == [
        '11111111-1111-4111-8111-111111111111'
    ]
    assert restored.source_key == record.source_key
    assert restored.source_release == record.source_release
    assert restored.projected_at_utc == record.projected_at_utc
    assert restored.payload.all() == record.payload.all()


def test_projection_record_rejects_system_profile_redefinition() -> None:
    document = profiles_projection_to_document(_projection_record())
    payload = document['payload']
    assert isinstance(payload, dict)
    payload['profiles'] = [
        {
            'key': 'root',
            'label': 'Replacement',
            'background_color': '#000000',
            'text_color': '#FFFFFF',
        }
    ]

    with pytest.raises(ProfilesConfigurationProjectionError):
        profiles_projection_from_document(document)


def test_projection_record_rejects_wrong_document_type() -> None:
    document = profiles_projection_to_document(_projection_record())
    document['document_type'] = 'wrong'

    with pytest.raises(ProfilesConfigurationProjectionError):
        profiles_projection_from_document(document)
