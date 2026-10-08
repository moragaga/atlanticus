from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmRouting,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    GroupLifecycleDecision,
    GroupLifecycleState,
    PlannedAlarm,
    reduce_group_cycle,
    reduce_initial_technical_incidents,
)
from ada.alarms.persistence.operational import (
    ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION,
    AlarmPersistence,
    EngineCommitRecord,
)
from ada.alarms.persistence.operational.core_commit_bridge import prepare_group_commit
from ada.alarms.persistence.operational.lifecycle_snapshot import restore_group_lifecycle
from ada.alarms.persistence.operational.technical_incidents import snapshot_technical_incidents
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality

from .support import mutation_fence

AT = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity('mill', 'risk')
GROUP = 'mill-feed'


def _evaluation(at: datetime, *, key: str | None) -> AlarmEvaluation:
    if key is not None:
        return AlarmEvaluation(
            alarm_identity=IDENTITY,
            status=AlarmStatus.ERROR,
            evaluated_at=at,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key=key,
                message='Input missing',
            ),
        )
    return AlarmEvaluation(
        alarm_identity=IDENTITY,
        status=AlarmStatus.INACTIVE,
        evaluated_at=at,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='threshold',
            contract_version='v1',
            payload={'value': 0},
        ),
    )


def _prepare(previous_snapshot, previous_state, at, previous_incidents, key):
    evaluation = _evaluation(at, key=key)
    reduced = reduce_initial_technical_incidents(
        previous_incidents,
        evaluations=(evaluation,),
        executable_groups={IDENTITY: GROUP},
        cycle_at=at,
    )
    prepared = prepare_group_commit(
        previous_snapshot=previous_snapshot,
        previous_state=previous_state,
        decision=GroupLifecycleDecision(state=previous_state),
        evaluations=(evaluation,),
        technical_incidents=reduced.open_incidents,
        technical_incident_changes=reduced.changes,
        cycle_at=at,
        committed_at=at,
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        runtime_artifact_version='runtime/1',
    )
    return prepared, reduced


def test_initial_technical_error_creates_v3_commit_without_occurrence() -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    prepared, reduced = _prepare(None, empty, AT, (), 'A')

    assert prepared is not None
    assert prepared.state == empty
    assert prepared.record.schema_version == ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION
    assert [item['kind'] for item in prepared.record.records['technical_incident_changes']] == [
        'STARTED'
    ]
    assert restore_group_lifecycle(prepared.record.snapshot_after) == empty
    assert snapshot_technical_incidents(prepared.record.snapshot_after) == reduced.open_incidents
    assert EngineCommitRecord.from_document(prepared.record.as_document()) == prepared.record


def test_repeated_identical_error_does_not_emit_new_commit() -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    first, reduced = _prepare(None, empty, AT, (), 'A')
    assert first is not None
    for count in range(1, 1201):
        at = AT + timedelta(seconds=count * 3)
        prepared, subsequent = _prepare(
            first.record.snapshot_after, empty, at, reduced.open_incidents, 'A'
        )
        assert prepared is None
        assert not subsequent.changes


def test_error_change_and_resolution_are_two_new_commits() -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    first, start = _prepare(None, empty, AT, (), 'A')
    assert first is not None
    changed, after_change = _prepare(
        first.record.snapshot_after, empty, AT + timedelta(seconds=3), start.open_incidents, 'B'
    )
    assert changed is not None
    assert changed.record.commit.previous_commit_id == first.record.commit.commit_id
    assert changed.record.records['technical_incident_changes'][0]['kind'] == 'CHANGED'
    resolved, after_resolution = _prepare(
        changed.record.snapshot_after,
        empty,
        AT + timedelta(seconds=6),
        after_change.open_incidents,
        None,
    )
    assert resolved is not None
    assert resolved.record.records['technical_incident_changes'][0]['kind'] == 'RESOLVED'
    assert after_resolution.open_incidents == ()
    assert snapshot_technical_incidents(resolved.record.snapshot_after) == ()


def test_preparation_rejects_stale_previous_state() -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    first, reduction = _prepare(None, empty, AT, (), 'A')
    assert first is not None
    with pytest.raises(ValueError, match='previous snapshot belongs'):
        prepare_group_commit(
            previous_snapshot=first.record.snapshot_after,
            previous_state=GroupLifecycleState(priority_group='different'),
            decision=GroupLifecycleDecision(state=GroupLifecycleState(priority_group='different')),
            evaluations=(),
            technical_incidents=reduction.open_incidents,
            technical_incident_changes=(),
            cycle_at=AT + timedelta(seconds=3),
            committed_at=AT + timedelta(seconds=3),
            alarm_configuration_revision='R42',
            tool_registry_revision='T18',
            runtime_artifact_version='runtime/1',
        )


def test_physical_start_creates_initial_evidence_and_roundtrip_state() -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    plan = PlannedAlarm(
        identity=IDENTITY,
        kind=AlarmKind.RISK,
        criticality=Criticality.C3,
        is_special_condition=False,
        priority_group=GROUP,
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        routing=AlarmRouting(origin_tool_key='tool-a', destinations=()),
    )
    evaluation = AlarmEvaluation(
        alarm_identity=IDENTITY,
        status=AlarmStatus.ACTIVE,
        evaluated_at=AT,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='threshold',
            contract_version='v1',
            payload={'value': 15, 'threshold': 10},
        ),
    )
    decision = reduce_group_cycle(
        empty,
        cycle_at=AT,
        planned_alarms=(plan,),
        evaluations=(evaluation,),
        occurrence_id_factory=lambda identity, at: 'O1',
        episode_id_factory=lambda group, at: 'E1',
    )
    prepared = prepare_group_commit(
        previous_snapshot=None,
        previous_state=empty,
        decision=decision,
        evaluations=(evaluation,),
        technical_incidents=(),
        technical_incident_changes=(),
        cycle_at=AT,
        committed_at=AT,
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        runtime_artifact_version='runtime/1',
    )
    assert prepared is not None
    assert len(prepared.record.records['evidence_records']) == 1
    assert prepared.record.records['evidence_records'][0]['payload'] == {
        'value': 15,
        'threshold': 10,
    }
    assert restore_group_lifecycle(prepared.record.snapshot_after) == prepared.state
    assert prepared.state.alarms[0].next_evidence_due_at == AT + timedelta(minutes=5)


def test_prepared_incident_commit_can_be_written_and_recovered(tmp_path) -> None:
    empty = GroupLifecycleState(priority_group=GROUP)
    prepared, reduction = _prepare(None, empty, AT, (), 'A')
    assert prepared is not None
    persistence = AlarmPersistence(application_root=tmp_path)
    persistence.commit_batch(
        (prepared.record,),
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    rebooted = AlarmPersistence(application_root=tmp_path)
    rebooted.recover(assert_authority=lambda: None, fenced_mutation=mutation_fence)
    assert snapshot_technical_incidents(rebooted.read_snapshot(GROUP)) == reduction.open_incidents
    prepared_again, _ = _prepare(
        rebooted.read_snapshot(GROUP),
        empty,
        AT + timedelta(seconds=3),
        reduction.open_incidents,
        'A',
    )
    assert prepared_again is None
