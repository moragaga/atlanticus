from datetime import UTC, datetime

import pytest

from ada.contracts.alarms import (
    ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
    ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmConfiguration,
    AlarmConfigurationProjection,
    AlarmConfigurationProjectionDependency,
    AlarmConfigurationProjectionValidationError,
    AlarmConfigurationSnapshot,
    alarm_configuration_projection_item_id,
)
from ada.contracts.tools import ToolDependencyManifest


def _projection() -> AlarmConfigurationProjection:
    return AlarmConfigurationProjection(
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        source_release_id='alarm-r2',
        source_published_at_utc=datetime(2026, 9, 22, 11, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 22, 11, 1, tzinfo=UTC),
        snapshot=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r4',
                tools=(),
            ),
        ),
        dependencies=(
            AlarmConfigurationProjectionDependency(
                source_key='other-source',
                source_release_id='other-r1',
                source_published_at_utc=datetime(2026, 9, 22, 9, tzinfo=UTC),
            ),
        ),
    )


def test_projection_round_trips_existing_persisted_shape() -> None:
    projection = _projection()

    document = projection.to_document(
        item_id='active',
        partition_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )

    assert document['document_type'] == ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE
    assert document['schema_version'] == ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION
    assert document['id'] == 'active'
    assert document['partition_key'] == ALARM_CONFIGURATION_SOURCE_KEY
    assert AlarmConfigurationProjection.from_document(document) == projection


def test_projection_fingerprint_ignores_cosmos_envelope_fields() -> None:
    projection = _projection()
    restored = AlarmConfigurationProjection.from_document(
        {
            **projection.to_document(),
            'id': 'cosmos-id',
            'partition_key': ALARM_CONFIGURATION_SOURCE_KEY,
            '_etag': 'etag',
        }
    )

    assert restored.fingerprint == projection.fingerprint


def test_projection_exposes_confirmed_tool_revision() -> None:
    assert _projection().confirmed_tool_catalog_revision == 'tools-r4'


@pytest.mark.parametrize(
    'mutate',
    [
        lambda value: value.update(document_type='wrong'),
        lambda value: value.update(schema_version=2),
        lambda value: value.update(payload={}),
        lambda value: value.update(source_published_at_utc='not-a-date'),
        lambda value: value.update(dependencies='invalid'),
    ],
)
def test_projection_rejects_invalid_documents(mutate) -> None:
    document = _projection().to_document()
    mutate(document)

    with pytest.raises(AlarmConfigurationProjectionValidationError):
        AlarmConfigurationProjection.from_document(document)


def test_projection_dependency_rejects_invalid_nested_dependency() -> None:
    document = _projection().to_document()
    document['dependencies'] = [
        {
            'source_key': 'other-source',
            'source_release_id': 'other-r1',
            'source_published_at_utc': '2026-09-22T09:00:00+00:00',
            'dependencies': ['invalid'],
        }
    ]

    with pytest.raises(AlarmConfigurationProjectionValidationError):
        AlarmConfigurationProjection.from_document(document)


def test_projection_item_id_preserves_published_identity_contract() -> None:
    assert (
        alarm_configuration_projection_item_id(ALARM_CONFIGURATION_SOURCE_KEY)
        == 'ada-command-center-alarm-configuration-projection-'
        'eff3875d752b9f8ab4e406943b6fc6ca6762585f38777e2c9f0053f4ea8aad57'
    )


def test_projection_item_id_rejects_invalid_source_key() -> None:
    with pytest.raises(ValueError):
        alarm_configuration_projection_item_id(' alarm-configuration ')
