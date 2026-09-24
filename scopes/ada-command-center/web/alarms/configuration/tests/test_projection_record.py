from datetime import UTC, datetime

import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyEntry, ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.configuration.projection_record import (
    ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
    alarm_configuration_projection_from_document,
    alarm_configuration_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

from .helpers import configuration


def _record() -> ProjectionRecord[AlarmConfigurationSnapshot]:
    return ProjectionRecord(
        source_key=SourceKey('alarm-configuration'),
        source_release_id=SourceReleaseId('alarm-r2'),
        source_published_at_utc=datetime(2026, 9, 22, 11, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 22, 11, 1, tzinfo=UTC),
        payload=AlarmConfigurationSnapshot(
            configuration=configuration(),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r4',
                tools=(
                    ToolDependencyEntry(
                        tool_key='tool_a',
                        display_name='Tool A',
                        source_release_id='tool-a-r1',
                        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                        structure=ToolStructure(
                            tool_key='tool_a',
                            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                            components=(
                                ToolComponent(
                                    key='mine',
                                    display_name='Mine',
                                    scope=ToolScope.MINE,
                                    subcomponents=(
                                        ToolSubcomponent(
                                            key='crusher',
                                            display_name='Crusher',
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_projection_record_preserves_frozen_evidence_and_exact_provenance() -> None:
    record = _record()
    document = alarm_configuration_projection_to_document(
        record,
        item_id='active',
        partition_key='alarm-configuration',
    )
    assert document['document_type'] == ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE
    assert document['id'] == 'active'
    assert document['partition_key'] == 'alarm-configuration'
    assert (
        document['payload']['tool_dependencies'] == record.payload.tool_dependencies.to_document()
    )
    assert document['dependencies'] == []
    restored = alarm_configuration_projection_from_document(document)
    assert restored == record
    assert restored.target == record.target


def test_projection_record_preserves_generic_projection_dependencies() -> None:
    original = _record()
    dependency = ProjectionTarget(
        source_key=SourceKey('other-source'),
        source_release=SourceReleaseRef(
            SourceReleaseId('other-release'),
            datetime(2026, 9, 22, 9, tzinfo=UTC),
        ),
    )
    record = ProjectionRecord(
        source_key=original.source_key,
        source_release_id=original.source_release_id,
        source_published_at_utc=original.source_published_at_utc,
        projected_at_utc=original.projected_at_utc,
        payload=original.payload,
        dependencies=(dependency,),
    )
    assert (
        alarm_configuration_projection_from_document(
            alarm_configuration_projection_to_document(record)
        )
        == record
    )


@pytest.mark.parametrize(
    'mutate',
    [
        lambda value: value.update(schema_version=2),
        lambda value: value.update(payload={}),
        lambda value: value.update(source_published_at_utc='not-a-date'),
        lambda value: value.update(dependencies='invalid'),
    ],
)
def test_projection_record_rejects_invalid_data(mutate) -> None:
    document = alarm_configuration_projection_to_document(_record())
    mutate(document)
    with pytest.raises(AlarmConfigurationProjectionError):
        alarm_configuration_projection_from_document(document)
