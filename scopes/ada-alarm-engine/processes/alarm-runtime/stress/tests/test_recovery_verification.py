from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
)
from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence
from stress.recovery_verification import verify_recovery


def _seed_volume(source):
    stamp = datetime.now(UTC).isoformat()
    basis = {'alarm_configuration_revision': 'stress-rev', 'tool_registry_revision': 'stress-tools'}
    store = IncrementalAlarmPersistence(application_root=source)
    store.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='stress-adoption',
            previous_artifact_ref=None,
            target_artifact_ref=AlarmArtifactRefSnapshot(
                source_key='alarm-configuration',
                result_id='alarm-materialization-' + 'a' * 64,
                manifest_sha256='b' * 64,
                alarm_configuration_revision=basis['alarm_configuration_revision'],
                confirmed_tool_catalog_revision=basis['tool_registry_revision'],
            ),
            effective_at=stamp,
            committed_at=stamp,
        ),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )
    record = EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id='stress-C1',
            cycle_id='stress-cycle-1',
            priority_group='mp10_test',
            previous_commit_id=None,
            evaluated_at=stamp,
            committed_at=stamp,
            alarm_configuration_revision=basis['alarm_configuration_revision'],
            tool_registry_revision=basis['tool_registry_revision'],
            runtime_artifact_version='ada-alarm-runtime-process/1.0.0',
            affected_alarms=('MP10/test_alarm',),
        ),
        snapshot_after=GroupRuntimeSnapshot(
            {
                'snapshot_schema_version': 'group-runtime-snapshot.v3',
                'priority_group': 'mp10_test',
                'last_commit_id': 'stress-C1',
                'state_basis': basis,
                'episode': None,
                'alarms': {},
                'technical_incidents': {},
            }
        ),
        records={},
    )
    store.commit_batch((record,), assert_authority=lambda: None, fenced_mutation=nullcontext)


def test_recovery_verification_continues_on_copy_without_changing_source(tmp_path):
    source = tmp_path / 'runtime'
    _seed_volume(source)
    head_path = source / 'alarms/runtime/state/journal-head.json'
    snapshot_path = source / 'alarms/runtime/state/groups/mp10_test.json'
    before_head = head_path.read_bytes()
    before_snapshot = snapshot_path.read_bytes()

    diagnostic = verify_recovery(application_root=source)

    assert diagnostic['status'] == 'verified', diagnostic
    assert diagnostic['error'] is None
    assert diagnostic['snapshots_preserved'] is True
    assert diagnostic['continuation_committed'] is True
    assert diagnostic['continuation_recovered'] is True
    assert diagnostic['continuation_position'] != diagnostic['durable_position']
    assert head_path.read_bytes() == before_head
    assert snapshot_path.read_bytes() == before_snapshot
    store = IncrementalAlarmPersistence(application_root=source)
    store.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    assert store.read_head().durable.as_document() == diagnostic['durable_position']


def test_recovery_verification_reports_missing_volume(tmp_path):
    diagnostic = verify_recovery(application_root=tmp_path / 'missing')
    assert diagnostic['status'] == 'failed'
    assert diagnostic['continuation_committed'] is False
    assert diagnostic['error'] == 'ValueError: Stress application volume does not exist'


def test_recovery_verification_rejects_uncommitted_genesis(tmp_path):
    source = tmp_path / 'empty'
    source.mkdir()
    diagnostic = verify_recovery(application_root=source)
    assert diagnostic['status'] == 'failed'
    assert diagnostic['continuation_committed'] is False
    assert diagnostic['error'] == 'AssertionError: Stress WAL head is not aligned and durable'
