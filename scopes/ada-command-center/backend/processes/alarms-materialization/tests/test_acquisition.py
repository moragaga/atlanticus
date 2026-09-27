from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.alarms import AlarmConfiguration, AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyEntry, ToolDependencyManifest
from ada_command_center.processes.alarms_materialization import (
    AlarmCandidateAcquirer,
    AlarmCandidateContractError,
    AlarmCandidateMismatchError,
    AlarmCandidateUnavailableError,
    compose_cosmos_alarm_candidate_acquirer,
)
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.projection.local import (
    LocalAlarmConfigurationProjectionStore,
    LocalAlarmConfigurationProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

SOURCE_KEY = SourceKey('alarm-configuration')
PUBLISHED = datetime(2026, 9, 26, 10, tzinfo=UTC)
PROJECTED = datetime(2026, 9, 26, 10, 1, tzinfo=UTC)


def _tool(tool_key: str = 'tool_a', name: str = 'Tool A') -> ToolDependencyEntry:
    return ToolDependencyEntry(
        tool_key=tool_key,
        display_name=name,
        source_release_id='tool-source-r4',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=ToolStructure(
            tool_key=tool_key,
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine',
                    display_name='Mine',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='crusher', display_name='Crusher'),),
                ),
            ),
        ),
    )


def _record(
    release: str = 'alarm-r10',
    tool_revision: str = 'catalog-c5',
    *,
    source_key: SourceKey = SOURCE_KEY,
) -> ProjectionRecord[AlarmConfigurationSnapshot]:
    return ProjectionRecord(
        source_key=source_key,
        source_release_id=SourceReleaseId(release),
        source_published_at_utc=PUBLISHED,
        projected_at_utc=PROJECTED,
        payload=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision=tool_revision,
                tools=(_tool(),),
            ),
        ),
    )


class _Projection:
    def __init__(self, record=None, failure=None):
        self.record = record
        self.failure = failure
        self.reads = []
        self.writes = []

    def get_active(self, source_key):
        self.reads.append(source_key)
        if self.failure is not None:
            raise self.failure
        return self.record

    def replace_active(self, projection):
        self.writes.append(projection)
        self.record = projection
        return projection


class _CosmosClient:
    def __init__(self):
        self.items = {}
        self.reads = []
        self.writes = []
        self.fail_read = False

    def find_item(self, *, container_name, item_id, partition_key):
        self.reads.append((container_name, item_id, partition_key))
        if self.fail_read:
            raise CosmosError('Cosmos read failed')
        return self.items.get((container_name, item_id, partition_key))

    def upsert_item(self, *, container_name, item):
        self.writes.append((container_name, item))
        document = dict(item)
        self.items[(container_name, document['id'], document['partition_key'])] = document
        return document


def test_acquisition_reads_active_projection_only_and_keeps_frozen_tool_evidence():
    projection = _Projection(_record())
    expected = SourceReleaseRef(SourceReleaseId('alarm-r10'), PUBLISHED)

    candidate = AlarmCandidateAcquirer(projection=projection, source_key=SOURCE_KEY).acquire(
        expected_release=expected
    )

    assert projection.reads == [SOURCE_KEY]
    assert projection.writes == []
    assert candidate.source_key == SOURCE_KEY
    assert candidate.source_release == expected
    assert candidate.alarm_configuration_revision == 'alarm-r10'
    assert candidate.confirmed_tool_catalog_revision == 'catalog-c5'
    assert candidate.projection == projection.record
    assert candidate.projection.projected_at_utc == PROJECTED
    tool = candidate.projection.payload.tool_dependencies.get('tool_a')
    assert tool.display_name == 'Tool A'
    assert tool.source_release_id == 'tool-source-r4'
    assert tool.structure.component('mine').display_name == 'Mine'
    assert tool.structure.component('mine').subcomponent('crusher').display_name == 'Crusher'


def test_acquisition_without_expected_release_pins_exact_active_projection():
    projection = _Projection(_record())
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=SOURCE_KEY).acquire()
    projection.record = _record('alarm-r11', 'catalog-c6')

    assert candidate.alarm_configuration_revision == 'alarm-r10'
    assert candidate.confirmed_tool_catalog_revision == 'catalog-c5'
    assert candidate.projection.payload.tool_dependencies.get('tool_a').display_name == 'Tool A'


def test_candidate_preserves_projection_dependency_metadata():
    dependency = ProjectionTarget(
        source_key=SourceKey('tool-reconciliation'),
        source_release=SourceReleaseRef(SourceReleaseId('tool-reconciliation-r2'), PUBLISHED),
    )
    record = replace(_record(), dependencies=(dependency,))

    candidate = AlarmCandidateAcquirer(
        projection=_Projection(record), source_key=SOURCE_KEY
    ).acquire()

    assert candidate.projection.dependencies == (dependency,)
    assert candidate.projection.source_release == record.source_release


def test_candidate_exposes_fresh_independent_decoded_projection_each_time():
    candidate = AlarmCandidateAcquirer(
        projection=_Projection(_record()), source_key=SOURCE_KEY
    ).acquire()
    first = candidate.projection
    second = candidate.projection

    assert first == second
    assert first is not second
    assert first.payload is not second.payload
    assert first.payload.tool_dependencies is not second.payload.tool_dependencies


def test_missing_active_projection_is_not_a_blocked_alarm_resolution():
    with pytest.raises(AlarmCandidateUnavailableError, match='unavailable'):
        AlarmCandidateAcquirer(projection=_Projection(), source_key=SOURCE_KEY).acquire()


def test_expected_release_id_mismatch_rejected():
    expected = SourceReleaseRef(SourceReleaseId('alarm-r9'), PUBLISHED)
    with pytest.raises(AlarmCandidateMismatchError, match='release mismatch'):
        AlarmCandidateAcquirer(projection=_Projection(_record()), source_key=SOURCE_KEY).acquire(
            expected_release=expected
        )


def test_expected_release_timestamp_mismatch_rejected():
    expected = SourceReleaseRef(SourceReleaseId('alarm-r10'), PUBLISHED + timedelta(seconds=1))
    with pytest.raises(AlarmCandidateMismatchError, match='release mismatch'):
        AlarmCandidateAcquirer(projection=_Projection(_record()), source_key=SOURCE_KEY).acquire(
            expected_release=expected
        )


def test_unexpected_source_key_rejected():
    with pytest.raises(AlarmCandidateMismatchError, match='source key mismatch'):
        AlarmCandidateAcquirer(
            projection=_Projection(_record(source_key=SourceKey('other-source'))),
            source_key=SOURCE_KEY,
        ).acquire()


def test_wrong_payload_rejected_as_contract_error():
    projection = _Projection(replace(_record(), payload=object()))
    with pytest.raises(AlarmCandidateContractError, match='contract is invalid'):
        AlarmCandidateAcquirer(projection=projection, source_key=SOURCE_KEY).acquire()


def test_operational_store_failure_propagates_without_fake_blocked_finding():
    failure = AlarmConfigurationProjectionError('Cosmos temporarily unavailable')
    with pytest.raises(AlarmConfigurationProjectionError) as raised:
        AlarmCandidateAcquirer(
            projection=_Projection(failure=failure), source_key=SOURCE_KEY
        ).acquire()
    assert raised.value is failure


def test_invalid_expected_release_type_is_rejected_before_reading():
    projection = _Projection(_record())
    with pytest.raises(TypeError, match='SourceReleaseRef'):
        AlarmCandidateAcquirer(projection=projection, source_key=SOURCE_KEY).acquire(
            expected_release='alarm-r10'
        )
    assert projection.reads == []


def test_cosmos_composition_reads_only_existing_projection_container():
    client = _CosmosClient()
    from ada_command_center.web.alarms.projection.cosmos import (
        CosmosAlarmConfigurationProjectionStore,
        CosmosAlarmConfigurationProjectionStoreSettings,
    )

    publisher = CosmosAlarmConfigurationProjectionStore(
        client=client,
        settings=CosmosAlarmConfigurationProjectionStoreSettings(container_name='alarm-projection'),
    )
    publisher.replace_active(_record())
    writes_before = len(client.writes)
    candidate = compose_cosmos_alarm_candidate_acquirer(
        cosmos_client=client,
        container_name='alarm-projection',
        source_key=SOURCE_KEY,
    ).acquire()

    assert candidate.alarm_configuration_revision == 'alarm-r10'
    assert candidate.confirmed_tool_catalog_revision == 'catalog-c5'
    assert candidate.projection.payload == _record().payload
    assert len(client.reads) == 1
    assert client.reads[0][0] == 'alarm-projection'
    assert client.reads[0][2] == SOURCE_KEY.value
    assert len(client.writes) == writes_before


def test_cosmos_composition_preserves_transport_errors():
    client = _CosmosClient()
    client.fail_read = True
    with pytest.raises(AlarmConfigurationProjectionError, match='Could not read Cosmos'):
        compose_cosmos_alarm_candidate_acquirer(
            cosmos_client=client, container_name='alarm-projection', source_key=SOURCE_KEY
        ).acquire()


def test_local_projection_store_roundtrip_for_acquirer(tmp_path: Path):
    store = LocalAlarmConfigurationProjectionStore(
        LocalAlarmConfigurationProjectionStoreSettings(root=tmp_path.absolute())
    )
    store.replace_active(_record())

    candidate = AlarmCandidateAcquirer(projection=store, source_key=SOURCE_KEY).acquire(
        expected_release=_record().source_release
    )

    assert candidate.projection == _record()
    assert candidate.projection.payload.tool_dependencies.get('tool_a') == _tool()
