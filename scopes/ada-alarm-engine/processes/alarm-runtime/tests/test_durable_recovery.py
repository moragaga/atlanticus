from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    GroupLifecycleState,
    reduce_initial_technical_incidents,
)
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    JournalHead,
    JournalPosition,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import snapshot_group_lifecycle
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.durable_recovery import (
    AlarmDurableRecovery,
    AlarmDurableRecoveryError,
)

from .support import engine_configuration

AT = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)


class LeaseContext:
    def __init__(self):
        self.checks = 0
        self.revoked = False

    def assert_lease_current(self):
        self.checks += 1
        if self.revoked:
            raise RuntimeError('lease lost')

    def fenced_mutation(self):
        return nullcontext()


class Store:
    def __init__(self, *, effective=None, snapshots=(), durable=False):
        self.effective = effective
        self.snapshots = snapshots
        self.events = []
        position = JournalPosition('2026-10-08T10Z#0000', 100, 'C1') if durable else None
        self.head = JournalHead(durable=position, materialized=position)

    def recover(self, *, assert_authority, fenced_mutation):
        self.events.append('recover')
        assert_authority()
        with fenced_mutation():
            assert_authority()

    def read_head(self):
        self.events.append('read_head')
        return self.head

    def read_effective_head(self):
        self.events.append('read_effective')
        return self.effective

    def list_snapshots(self):
        self.events.append('list_snapshots')
        return self.snapshots


class ReadyReader:
    def __init__(self, configuration):
        self.configuration = configuration
        self.calls = []
        self.override_result_id = None

    def read_ready(self, *, source_key, result_id, expected_manifest_sha256=None):
        self.calls.append((source_key, result_id, expected_manifest_sha256))
        return SimpleNamespace(
            result_id=self.override_result_id or result_id,
            manifest_sha256=expected_manifest_sha256,
            engine=self.configuration,
            manifest=SimpleNamespace(resolution_key=self.configuration.resolution_key),
        )


def _reference():
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='b' * 64,
        alarm_configuration_revision='ALARMS-7',
        confirmed_tool_catalog_revision='TOOLS-4',
    )


def _recovery(store=None, ready=None):
    return AlarmDurableRecovery(
        persistence=Store() if store is None else store,
        materializations=ReadyReader(engine_configuration()) if ready is None else ready,
        source_key='alarm-configuration',
    )


def _snapshot(*, group='mill_feed', incidents=()):
    return snapshot_group_lifecycle(
        GroupLifecycleState(priority_group=group),
        commit_id='C1',
        alarm_configuration_revision='ALARMS-7',
        tool_registry_revision='TOOLS-4',
        technical_incidents=incidents,
    )


def _incident():
    identity = AlarmIdentity('mill', 'risk')
    evaluation = AlarmEvaluation(
        alarm_identity=identity,
        status=AlarmStatus.ERROR,
        evaluated_at=AT,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.QUALITY,
            error_key='missing_data',
            message='missing data',
        ),
    )
    return reduce_initial_technical_incidents(
        (),
        evaluations=(evaluation,),
        executable_groups={identity: 'mill_feed'},
        cycle_at=AT,
    ).open_incidents[0]


def test_first_bootstrap_without_wal_returns_no_pinned_authority():
    store = Store()
    context = LeaseContext()
    result = _recovery(store=store).recover(context)

    assert result.lifecycle is None
    assert result.artifact_ref is None
    assert result.group_commit_ids == ()
    assert store.events[:3] == ['recover', 'read_head', 'read_effective']
    assert context.checks >= 3


def test_exact_effective_artifact_is_loaded_without_using_latest_pointer():
    reference = _reference()
    store = Store(effective=SimpleNamespace(target_artifact_ref=reference), durable=True)
    reader = ReadyReader(engine_configuration())
    result = _recovery(store=store, ready=reader).recover(LeaseContext())

    assert result.artifact_ref == reference
    assert result.lifecycle.configuration == reader.configuration
    assert result.lifecycle.groups == ()
    assert reader.calls == [('alarm-configuration', reference.result_id, reference.manifest_sha256)]


def test_v3_snapshot_restores_open_incident_and_group_commit_head():
    reference = _reference()
    incident = _incident()
    snapshot = _snapshot(incidents=(incident,))
    store = Store(
        effective=SimpleNamespace(target_artifact_ref=reference),
        snapshots=(snapshot,),
        durable=True,
    )
    result = _recovery(store=store).recover(LeaseContext())

    assert result.lifecycle.technical_incidents == (incident,)
    assert result.lifecycle.groups == (GroupLifecycleState(priority_group='mill_feed'),)
    assert result.group_commit_ids == (('mill_feed', 'C1'),)


def test_legacy_snapshot_requires_explicit_recovery_migration():
    legacy = _snapshot().as_document()
    legacy['snapshot_schema_version'] = 'group-runtime-snapshot.v2'
    from ada.alarms.persistence.operational import GroupRuntimeSnapshot

    snapshot = GroupRuntimeSnapshot(legacy)
    store = Store(
        effective=SimpleNamespace(target_artifact_ref=_reference()),
        snapshots=(snapshot,),
        durable=True,
    )
    with pytest.raises(ValueError, match='v3'):
        _recovery(store=store).recover(LeaseContext())


def test_snapshot_basis_cannot_differ_from_effective_artifact():
    snapshot = snapshot_group_lifecycle(
        GroupLifecycleState(priority_group='mill_feed'),
        commit_id='C1',
        alarm_configuration_revision='OLD',
        tool_registry_revision='TOOLS-4',
        technical_incidents=(),
    )
    store = Store(
        effective=SimpleNamespace(target_artifact_ref=_reference()),
        snapshots=(snapshot,),
        durable=True,
    )
    with pytest.raises(AlarmDurableRecoveryError, match='snapshot revisions'):
        _recovery(store=store).recover(LeaseContext())


def test_incomplete_legacy_durable_wal_cannot_be_silently_bootstrapped():
    store = Store(durable=True)
    with pytest.raises(AlarmDurableRecoveryError, match='migration'):
        _recovery(store=store).recover(LeaseContext())


def test_ready_result_identity_is_verified_not_just_requested():
    reader = ReadyReader(engine_configuration())
    reader.override_result_id = 'alarm-materialization-' + 'c' * 64
    store = Store(
        effective=SimpleNamespace(target_artifact_ref=_reference()),
        durable=True,
    )
    with pytest.raises(AlarmDurableRecoveryError, match='READY artifact identity'):
        _recovery(store=store, ready=reader).recover(LeaseContext())


def test_ready_resolution_revision_must_match_effective():
    reader = ReadyReader(engine_configuration(release='ALARMS-8'))
    store = Store(
        effective=SimpleNamespace(target_artifact_ref=_reference()),
        durable=True,
    )
    with pytest.raises(AlarmDurableRecoveryError, match='READY revisions'):
        _recovery(store=store, ready=reader).recover(LeaseContext())


def test_lost_lease_aborts_before_reading_published_state():
    context = LeaseContext()
    context.revoked = True
    store = Store()
    reader = ReadyReader(engine_configuration())
    with pytest.raises(RuntimeError, match='lease lost'):
        _recovery(store=store, ready=reader).recover(context)
    assert store.events == []
    assert reader.calls == []


def test_effective_source_cannot_be_crossed_with_another_application():
    store = Store(
        effective=SimpleNamespace(
            target_artifact_ref=replace(_reference(), source_key='different-source')
        ),
        durable=True,
    )
    with pytest.raises(AlarmDurableRecoveryError, match='source'):
        _recovery(store=store).recover(LeaseContext())


def test_wal_head_change_during_recovery_is_rejected():
    class ChangedHeadStore(Store):
        def read_head(self):
            original = super().read_head()
            if self.events.count('read_head') == 1:
                return original
            next_position = JournalPosition('2026-10-08T10Z#0000', 130, 'C2')
            return JournalHead(durable=next_position, materialized=next_position)

    store = ChangedHeadStore(
        effective=SimpleNamespace(target_artifact_ref=_reference()),
        durable=True,
    )
    with pytest.raises(AlarmDurableRecoveryError, match='head changed'):
        _recovery(store=store).recover(LeaseContext())
