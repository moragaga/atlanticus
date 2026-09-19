from datetime import UTC, datetime

import pytest

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.projection_record import (
    ADA_ACCESS_PROJECTION_DOCUMENT_TYPE,
    ADA_ACCESS_PROJECTION_SCHEMA_VERSION,
    ada_access_projection_from_document,
    ada_access_projection_to_document,
)
from ada.web.access.models import ProfileAccessGrant
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _target(
    source_key: str,
    release_id: str,
    *,
    hour: int,
    dependencies: tuple[ProjectionTarget, ...] = (),
) -> ProjectionTarget:
    return ProjectionTarget(
        source_key=SourceKey(source_key),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(release_id),
            published_at_utc=datetime(2026, 9, 19, hour, tzinfo=UTC),
        ),
        dependencies=dependencies,
    )


def _record() -> ProjectionRecord[AdaAccessConfiguration]:
    upstream = _target('profiles-source', 'profiles-source-1', hour=9)
    profiles = _target(
        'profiles-configuration',
        'profiles-1',
        hour=10,
        dependencies=(upstream,),
    )
    return ProjectionRecord(
        source_key=SourceKey('ada-access'),
        source_release_id=SourceReleaseId('access-1'),
        source_published_at_utc=datetime(2026, 9, 19, 11, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 19, 11, 1, tzinfo=UTC),
        payload=AdaAccessConfiguration(
            profile_access=(
                ProfileAccessGrant(
                    profile_key='11111111-1111-4111-8111-111111111111',
                    access_keys=('alarms.view', 'alarms.manage'),
                ),
            )
        ),
        dependencies=(profiles,),
    )


def test_projection_record_round_trips_exact_target_payload_and_timestamps() -> None:
    record = _record()

    document = ada_access_projection_to_document(record)
    restored = ada_access_projection_from_document(document)

    assert restored == record
    assert restored.target == record.target
    assert restored.dependencies == record.dependencies


def test_projection_record_document_supports_provider_identity_fields() -> None:
    document = ada_access_projection_to_document(
        _record(),
        item_id='projection-id',
        partition_key='ada-access',
    )

    assert document['document_type'] == ADA_ACCESS_PROJECTION_DOCUMENT_TYPE
    assert document['schema_version'] == ADA_ACCESS_PROJECTION_SCHEMA_VERSION
    assert document['id'] == 'projection-id'
    assert document['partition_key'] == 'ada-access'


def test_projection_record_rejects_wrong_document_type() -> None:
    document = ada_access_projection_to_document(_record())
    document['document_type'] = 'wrong'

    with pytest.raises(AdaAccessConfigurationProjectionError):
        ada_access_projection_from_document(document)


def test_projection_record_rejects_wrong_schema_version() -> None:
    document = ada_access_projection_to_document(_record())
    document['schema_version'] = 2

    with pytest.raises(AdaAccessConfigurationProjectionError):
        ada_access_projection_from_document(document)


def test_projection_record_rejects_corrupt_dependencies() -> None:
    document = ada_access_projection_to_document(_record())
    document['dependencies'] = [{'source_key': 'profiles-configuration'}]

    with pytest.raises(AdaAccessConfigurationProjectionError):
        ada_access_projection_from_document(document)
