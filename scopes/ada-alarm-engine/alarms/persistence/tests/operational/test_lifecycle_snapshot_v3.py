from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ada.alarms.core import (
    AlarmEpisode,
    AlarmEvaluation,
    AlarmOccurrence,
    AlarmRuntimeState,
    AlarmStatus,
    DeactivationEffect,
    EvaluationError,
    EvaluationErrorOrigin,
    GroupLifecycleState,
    ManagementEffect,
    PendingToolAssignment,
    RuntimeEvaluationState,
    TechnicalHold,
    ToolAssignment,
    reduce_initial_technical_incidents,
)
from ada.alarms.persistence.operational import (
    ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION,
    GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
    snapshot_technical_incidents,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import (
    restore_group_lifecycle,
    snapshot_group_lifecycle,
)
from ada.contracts.alarms import AlarmIdentity

from .support import build_snapshot, mutation_fence

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity(family_key='mill', alarm_key='pressure')


def _group(*, error: bool = False, with_effects: bool = True) -> GroupLifecycleState:
    occurrence = AlarmOccurrence(
        occurrence_id='O1',
        alarm_identity=IDENTITY,
        episode_id='E1',
        started_at=NOW,
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
    )
    evaluation = RuntimeEvaluationState(
        status=AlarmStatus.ERROR if error else AlarmStatus.ACTIVE,
        evaluated_at=NOW + timedelta(minutes=1),
        error_key='missing_data' if error else None,
    )
    runtime = AlarmRuntimeState(
        alarm_identity=IDENTITY,
        occurrence=occurrence,
        last_evaluation=evaluation,
        management_cycle=2,
        technical_hold=(
            TechnicalHold(
                started_at=NOW + timedelta(minutes=1),
                due_at=NOW + timedelta(minutes=6),
            )
            if error
            else None
        ),
        management_effect=(
            ManagementEffect(
                effect_id='M1',
                source_occurrence_id='O1',
                effective_at=NOW,
                reappearance_due_at=None,
            )
            if with_effects
            else None
        ),
        deactivation_effect=(
            DeactivationEffect(
                effect_id='D1',
                source_occurrence_id='O1',
                effective_from=NOW,
                effective_until=NOW + timedelta(hours=4),
            )
            if with_effects
            else None
        ),
        assignments=(ToolAssignment(tool_key='tool-a', assigned_at=NOW),),
        pending_assignments=(
            PendingToolAssignment(tool_key='tool-b', due_at=NOW + timedelta(minutes=15)),
        ),
        next_evidence_due_at=(None if error else NOW + timedelta(minutes=5)),
    )
    return GroupLifecycleState(
        priority_group='mill-feed',
        episode=AlarmEpisode(episode_id='E1', priority_group='mill-feed', started_at=NOW),
        alarms=(runtime,),
    )


def _snapshot(state: GroupLifecycleState) -> GroupRuntimeSnapshot:
    return snapshot_group_lifecycle(
        state,
        commit_id='C1',
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        technical_incidents=(),
    )


def _commit(snapshot: GroupRuntimeSnapshot) -> EngineCommitRecord:
    return EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id='C1',
            cycle_id='20261008T100000000000Z',
            priority_group='mill-feed',
            previous_commit_id=None,
            evaluated_at='2026-10-08T10:00:00Z',
            committed_at='2026-10-08T10:00:00Z',
            alarm_configuration_revision='R42',
            tool_registry_revision='T18',
            runtime_artifact_version='alarm-runtime.v1',
            affected_alarms=(IDENTITY.canonical_key,),
        ),
        snapshot_after=snapshot,
        records={},
    )


@pytest.mark.parametrize('error', [False, True])
@pytest.mark.parametrize('with_effects', [False, True])
def test_lossless_roundtrip_of_group_lifecycle(error: bool, with_effects: bool) -> None:
    original = _group(error=error, with_effects=with_effects)
    snapshot = _snapshot(original)

    assert (
        snapshot.as_document()['snapshot_schema_version']
        == GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION
    )
    assert (
        restore_group_lifecycle(GroupRuntimeSnapshot.from_document(snapshot.as_document()))
        == original
    )


def test_v3_preserves_management_only_state_without_occurrence() -> None:
    group = GroupLifecycleState(
        priority_group='other',
        alarms=(
            AlarmRuntimeState(
                alarm_identity=IDENTITY,
                deactivation_effect=DeactivationEffect(
                    effect_id='D2',
                    source_occurrence_id='O2',
                    effective_from=NOW,
                    effective_until=NOW + timedelta(hours=1),
                ),
            ),
        ),
    )
    snapshot = _snapshot(group)

    assert restore_group_lifecycle(snapshot) == group


def test_v3_commit_record_roundtrip_and_hash() -> None:
    record = _commit(_snapshot(_group()))

    assert record.as_document()['record_schema_version'] == ENGINE_COMMIT_RECORD_V3_SCHEMA_VERSION
    assert EngineCommitRecord.from_document(record.as_document()) == record


def test_persist_and_reload_from_durable_wal(tmp_path: Path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    state = _group(error=True)
    record = _commit(_snapshot(state))

    store.commit_batch(
        [record],
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    restarted = AlarmPersistence(application_root=tmp_path)
    recovered = restarted.recover(
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )

    assert recovered.durable == recovered.materialized
    assert restore_group_lifecycle(restarted.read_snapshot('mill-feed')) == state


def test_v3_rejects_missing_deactivation_source_occurrence() -> None:
    document = deepcopy(_snapshot(_group()).as_document())
    del document['alarms'][IDENTITY.canonical_key]['deactivation_effect']['source_occurrence_id']

    with pytest.raises(AlarmPersistenceCorruptionError, match='deactivation_effect'):
        GroupRuntimeSnapshot.from_document(document)


def test_v1_snapshot_remains_readable_but_not_losslessly_recoverable() -> None:
    legacy = build_snapshot()
    reconstructed = GroupRuntimeSnapshot.from_document(legacy.as_document())

    assert reconstructed == legacy
    with pytest.raises(ValueError, match='requires snapshot v3'):
        restore_group_lifecycle(reconstructed)


def test_snapshot_invalid_technical_incident_is_rejected() -> None:
    document = deepcopy(_snapshot(_group()).as_document())
    document['technical_incidents'] = {'mill/other': {'invalid': True}}

    with pytest.raises(AlarmPersistenceCorruptionError, match='technical incident'):
        GroupRuntimeSnapshot.from_document(document)


def test_snapshot_preserves_open_technical_incidents_independently_of_physical_state() -> None:
    error = AlarmEvaluation(
        alarm_identity=IDENTITY,
        status=AlarmStatus.ERROR,
        evaluated_at=NOW,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.QUALITY,
            error_key='missing_data',
            message='No samples',
        ),
    )
    reduced = reduce_initial_technical_incidents(
        (),
        evaluations=(error,),
        executable_groups={IDENTITY: 'mill-feed'},
        cycle_at=NOW,
    )
    snapshot = snapshot_group_lifecycle(
        GroupLifecycleState(priority_group='mill-feed'),
        commit_id='C1',
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        technical_incidents=reduced.open_incidents,
    )

    assert restore_group_lifecycle(snapshot) == GroupLifecycleState(priority_group='mill-feed')
    assert snapshot_technical_incidents(snapshot) == reduced.open_incidents
