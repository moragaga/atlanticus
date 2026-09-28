from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent

from ada_command_center.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationContext,
    EvidenceContractRef,
    EvidenceSnapshot,
    GroupLifecycleState,
    materialize_group_commit,
    reduce_group_cycle,
)
from ada_command_center.alarms.materialization import (
    LocalAlarmMaterializationReader,
    materialization_root,
)
from ada_command_center.alarms.persistence import ConfigurationAdoptionRecordV2
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada_command_center.domain.tools import ToolDependencyEntry, ToolDependencyManifest
from ada_command_center.processes.alarms_materialization.acquisition import AlarmCandidateAcquirer
from ada_command_center.processes.alarms_materialization.job import (
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
)
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublisher,
    LocalAlarmMaterializationResultStore,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    JsonFileAlarmQualificationProvider,
)
from ada_command_center.processes.alarms_runtime import (
    AlarmConfigurationAdoptionExecutor,
    AlarmConfiguredIterationExecutor,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmExecutionSession,
    AlarmIterationLoader,
    AlarmOperationalCycle,
    AlarmOperationalCycleError,
    AlarmOperationalCycleResult,
    AlarmOperationalCycleRunner,
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobComposition,
    RuntimeLocalConfigurationReader,
    build_alarm_runtime_composition,
)
from atlanticus.kernel import Environment
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataRuntimeContext,
    DataSource,
)
from atlanticus.operational_data.planner import DataLoadPlan
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE = SourceKey('alarm-configuration')
_PUBLISHED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
_AT = _PUBLISHED + timedelta(hours=1)
_IDENTITY = AlarmIdentity(family_key='mill', alarm_key='risk')


@dataclass(slots=True)
class _ControlledProjection:
    record: ProjectionRecord

    def get_active(self, source_key: SourceKey) -> ProjectionRecord:
        assert source_key == _SOURCE
        return self.record


class _CommitClock:
    def committed_at(self, *, cycle_at: datetime) -> datetime:
        return cycle_at


def _rule(*, is_active: bool = True) -> AlarmDefinition:
    return AlarmDefinition(
        identity=_IDENTITY,
        rule_name='risk-rule',
        display_name='Risk',
        title='Risk alarm',
        cause_template='Value exceeds threshold',
        is_active=is_active,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        evaluator_key='threshold',
        parameters={'limit': 10.0},
        priority_group='mill-feed',
        priority_order=1,
        message_keys=(),
        reappearance=ReappearanceDefinition(),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True, max_duration_hours=4, approval_required=True
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='tool_a'),
        visual_targets=(),
    )


def _record(revision: str, *, is_active: bool = True) -> ProjectionRecord:
    kind = ToolConfigurationKind.PROCESS
    structure = ToolStructure(
        tool_key='tool_a',
        kind=kind,
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
                subcomponents=(ToolSubcomponent(key='pressure', display_name='Pressure'),),
            ),
        ),
        operational_scope=ToolScope.PLANT,
    )
    return ProjectionRecord(
        source_key=_SOURCE,
        source_release_id=SourceReleaseId(revision),
        source_published_at_utc=_PUBLISHED,
        projected_at_utc=_PUBLISHED + timedelta(minutes=1),
        payload=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(_rule(is_active=is_active),), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='catalog-c5',
                tools=(
                    ToolDependencyEntry(
                        tool_key='tool_a',
                        display_name='Tool A',
                        source_release_id='tool-r1',
                        kind=kind,
                        structure=structure,
                    ),
                ),
            ),
        ),
    )


def _write_qualification(
    path: Path,
    *,
    revision: str,
    qualified_at: str,
    evaluator_qualified: bool = True,
) -> None:
    path.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'source_key': _SOURCE.value,
                'source_release_id': revision,
                'source_published_at_utc': _PUBLISHED.isoformat(),
                'confirmed_tool_catalog_revision': 'catalog-c5',
                'qualified_at_utc': qualified_at,
                'producer': 'controlled-integration',
                'evidence_ref': 'qualification-controlled',
                'green_tool_keys': ['tool_a'],
                'qualified_evaluators': (
                    [{'family_key': 'mill', 'evaluator_key': 'threshold'}]
                    if evaluator_qualified
                    else []
                ),
            }
        ),
        encoding='utf-8',
    )


def _runtime_configuration(volume: Path) -> RuntimeConfiguration:
    return RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=volume,
    )


def _context(volume: Path, *, service_name: str, run_id: str) -> JobRuntimeContext:
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name=f'ada_command_center.processes.{service_name.replace("-", "_")}',
            service_name=service_name,
        ),
        configuration=_runtime_configuration(volume),
        run_id=run_id,
        correlation_id=f'correlation-{run_id}',
        wall_clock=lambda: _AT,
    )

    @contextmanager
    def fence():
        yield

    context._bind_lease_authority(generation=1, checker=lambda: None, fence=fence)
    return context


def _materialization_job(
    *, volume: Path, projection: _ControlledProjection, qualification_file: Path
) -> AlarmMaterializationJob:
    return AlarmMaterializationJob(
        acquirer=AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE),
        qualifications=JsonFileAlarmQualificationProvider(qualification_file),
        publisher=AlarmMaterializationPublisher(
            LocalAlarmMaterializationResultStore(root=materialization_root(volume))
        ),
    )


def _publish(job: AlarmMaterializationJob, volume: Path, *, run_id: str):
    context = _context(volume, service_name='alarms-materialization', run_id=run_id)
    context._begin_iteration(1)
    return job.run_iteration(context)


def _not_yet_executed(*args, **kwargs):
    raise AssertionError('B2c.3a does not execute operational evaluators')


def _runtime_job(volume: Path, *, run_id: str):
    composition = build_alarm_runtime_composition(
        runtime_configuration=_runtime_configuration(volume)
    )
    executions = []
    executor = AlarmConfiguredIterationExecutor(
        reader=RuntimeLocalConfigurationReader(volume_path=volume, source_key=_SOURCE.value),
        evaluator_registry=AlarmEvaluatorRegistry(
            contracts=(
                AlarmEvaluatorContract(
                    family_key='mill', evaluator_key='threshold', evaluator=_not_yet_executed
                ),
            )
        ),
        adoption_executor=AlarmConfigurationAdoptionExecutor(
            composition=composition,
            commit_time_provider=_CommitClock(),
            runtime_artifact_version='1.0.0',
        ),
        run_cycle=lambda context, session: executions.append(session),
        clock=lambda: _AT,
        adoption_id_factory=lambda: (
            f'adoption-{len(composition.durability.persistence.read_durable_adoptions()) + 1}'
        ),
    )
    job = AlarmRuntimeJobComposition(composition=composition, iteration_executor=executor)
    context = _context(volume, service_name='alarms-runtime', run_id=run_id)
    job.recover(context)
    return job, context, executions


def _reader(volume: Path) -> LocalAlarmMaterializationReader:
    return LocalAlarmMaterializationReader(root=materialization_root(volume))


def test_real_producer_to_runtime_pins_a_and_adopts_b_only_on_new_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    runtime, context, executed = _runtime_job(volume, run_id='runtime-a')
    first = runtime.iteration(context)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert first.cycle_executed is False
    assert context._next_iteration_delay() == 30.0
    assert executed == []

    result_a = _publish(materialization, volume, run_id='materialization-a')
    assert result_a.outcome is AlarmMaterializationOutcome.READY
    published_a = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    assert published_a is not None
    assert published_a.result_id == result_a.result_id
    assert published_a.runtime.resolution_key == published_a.delivery.resolution_key
    assert tuple(item.identity for item in published_a.runtime.planned_alarms) == (_IDENTITY,)
    version_a = materialization_root(volume) / 'versions' / result_a.result_id
    assert {item.name for item in version_a.iterdir()} == {
        'manifest.json',
        'runtime.json',
        'delivery.json',
    }

    context._begin_iteration(2)
    started = runtime.iteration(context)
    assert started.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert started.cycle_executed is True
    session_a = executed[0]
    assert session_a.alarm_configuration_revision == 'alarm-r10'
    assert session_a.entry_for(_IDENTITY).parameters['limit'] == 10.0
    persistence = runtime.composition.durability.persistence
    effective_a = persistence.read_effective_head()
    assert effective_a.target_artifact_ref.result_id == published_a.result_id
    assert effective_a.target_artifact_ref.manifest_sha256 == published_a.manifest_sha256
    assert len(persistence.read_durable_adoptions()) == 1

    projection.record = _record('alarm-r11')
    _write_qualification(
        evidence_file, revision='alarm-r11', qualified_at='2026-09-27T12:03:00+00:00'
    )
    result_b = _publish(materialization, volume, run_id='materialization-b')
    assert result_b.outcome is AlarmMaterializationOutcome.READY
    published_b = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    assert published_b.result_id == result_b.result_id != result_a.result_id
    assert (
        _reader(volume).read_exact_ready(
            source_key=_SOURCE.value,
            result_id=published_a.result_id,
            manifest_sha256=published_a.manifest_sha256,
        )
        == published_a
    )

    def forbidden(*args, **kwargs):
        pytest.fail('A pinned job must not reopen configuration readers')

    with monkeypatch.context() as patch:
        patch.setattr(RuntimeLocalConfigurationReader, 'load_ready_candidate', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'load_effective_revision', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'assert_current_effective', forbidden)
        for number in (3, 4):
            context._begin_iteration(number)
            cycle = runtime.iteration(context)
            assert cycle.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
            assert cycle.cycle_executed is True
            assert executed[-1] is session_a

    assert persistence.read_effective_head() == effective_a
    assert len(persistence.read_durable_adoptions()) == 1

    next_runtime, next_context, next_executed = _runtime_job(volume, run_id='runtime-b')
    selected_b = next_runtime.iteration(next_context)
    assert selected_b.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert selected_b.cycle_executed is True
    assert len(next_executed) == 1
    assert next_executed[0].alarm_configuration_revision == 'alarm-r11'
    assert next_executed[0] is not session_a
    next_persistence = next_runtime.composition.durability.persistence
    effective_b = next_persistence.read_effective_head()
    assert effective_b.target_artifact_ref.result_id == published_b.result_id
    assert effective_b.target_artifact_ref.manifest_sha256 == published_b.manifest_sha256
    assert len(next_persistence.read_durable_adoptions()) == 2


def test_real_blocked_materialization_preserves_ready_and_effective(tmp_path: Path) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    ready_a = _publish(materialization, volume, run_id='materialization-a')
    pinned = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    runtime, context, executions = _runtime_job(volume, run_id='runtime-a')
    assert runtime.iteration(context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    )
    assert len(executions) == 1
    original_head = runtime.composition.durability.persistence.read_effective_head()

    projection.record = _record('alarm-r11')
    _write_qualification(
        evidence_file,
        revision='alarm-r11',
        qualified_at='2026-09-27T12:03:00+00:00',
        evaluator_qualified=False,
    )
    blocked = _publish(materialization, volume, run_id='materialization-blocked')
    assert blocked.outcome is AlarmMaterializationOutcome.BLOCKED
    assert blocked.result_id != ready_a.result_id
    blocked_root = materialization_root(volume) / 'versions' / blocked.result_id
    assert {item.name for item in blocked_root.iterdir()} == {'manifest.json'}
    assert json.loads((blocked_root / 'manifest.json').read_text())['status'] == 'BLOCKED'
    assert _reader(volume).read_published_ready(source_key=_SOURCE.value) == pinned
    context._begin_iteration(2)
    assert runtime.iteration(context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    )
    assert executions[1] is executions[0]
    assert runtime.composition.durability.persistence.read_effective_head() == original_head

    next_runtime, next_context, next_executions = _runtime_job(volume, run_id='runtime-b')
    assert next_runtime.iteration(next_context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    )
    assert len(next_executions) == 1
    assert next_executions[0].alarm_configuration_revision == 'alarm-r10'
    assert len(next_runtime.composition.durability.persistence.read_durable_adoptions()) == 1

    _write_qualification(
        evidence_file, revision='alarm-r11', qualified_at='2026-09-27T12:04:00+00:00'
    )
    recovered = _publish(materialization, volume, run_id='materialization-requalified')
    assert recovered.outcome is AlarmMaterializationOutcome.READY
    assert recovered.result_id not in {ready_a.result_id, blocked.result_id}
    assert _reader(volume).read_published_ready(source_key=_SOURCE.value).result_id == (
        recovered.result_id
    )
    newest_runtime, newest_context, newest_executions = _runtime_job(volume, run_id='runtime-c')
    assert newest_runtime.iteration(newest_context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.ADOPTED
    )
    assert newest_executions[0].alarm_configuration_revision == 'alarm-r11'
    assert (
        newest_runtime.composition.durability.persistence.read_effective_head().target_artifact_ref.result_id
        == recovered.result_id
    )


def test_new_job_restores_exact_effective_without_ready_pointer(tmp_path: Path) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    _publish(materialization, volume, run_id='materialization-a')
    published = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    runtime, context, _ = _runtime_job(volume, run_id='runtime-a')
    assert runtime.iteration(context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    )
    (materialization_root(volume) / 'ready.json').unlink()

    restarted, new_context, executed = _runtime_job(volume, run_id='runtime-b')
    result = restarted.iteration(new_context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert result.cycle_executed is True
    assert executed[0].alarm_configuration_revision == 'alarm-r10'
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1
    head = restarted.composition.durability.persistence.read_effective_head()
    assert head.target_artifact_ref.result_id == published.result_id
    assert head.target_artifact_ref.manifest_sha256 == published.manifest_sha256


def test_corrupt_initial_ready_from_real_producer_waits_then_bootstraps(tmp_path: Path) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    published = _publish(materialization, volume, run_id='materialization-a')
    manifest = materialization_root(volume) / 'versions' / published.result_id / 'manifest.json'
    original = manifest.read_bytes()
    manifest.write_bytes(original + b' ')

    runtime, context, executed = _runtime_job(volume, run_id='runtime-a')
    waiting = runtime.iteration(context)
    assert waiting.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert waiting.cycle_executed is False
    assert context._next_iteration_delay() == 30.0
    assert len(runtime.composition.durability.persistence.read_durable_adoptions()) == 0
    assert executed == []

    manifest.write_bytes(original)
    context._begin_iteration(2)
    started = runtime.iteration(context)
    assert started.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert started.cycle_executed is True
    assert len(executed) == 1
    assert len(runtime.composition.durability.persistence.read_durable_adoptions()) == 1


def test_real_producer_v2_closes_active_group_only_in_next_job(tmp_path: Path) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    result_a = _publish(materialization, volume, run_id='materialization-a')
    assert result_a.outcome is AlarmMaterializationOutcome.READY
    published_a = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    assert published_a is not None

    runtime_a, context_a, executions_a = _runtime_job(volume, run_id='runtime-a')
    assert runtime_a.iteration(context_a).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    )
    session_a = executions_a[0]
    assert session_a.identities == (_IDENTITY,)
    persistence = runtime_a.composition.durability.persistence
    effective_a = persistence.read_effective_head()
    assert effective_a.target_artifact_ref.result_id == published_a.result_id
    assert persistence.read_durable_records() == ()

    operational_at = _AT + timedelta(seconds=1)
    empty_group = GroupLifecycleState(priority_group='mill-feed')
    evaluation = AlarmEvaluation(
        alarm_identity=_IDENTITY,
        status=AlarmStatus.ACTIVE,
        evaluated_at=operational_at,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='threshold', contract_version='v1', payload={'value': 11.0}
        ),
    )
    decision = reduce_group_cycle(
        empty_group,
        cycle_at=operational_at,
        planned_alarms=session_a.planned_alarms,
        evaluations=(evaluation,),
        occurrence_id_factory=lambda identity, when: 'occurrence-a',
        episode_id_factory=lambda group, when: 'episode-a',
    )
    assert decision.state.episode is not None
    assert decision.state.alarms[0].occurrence is not None
    seed = materialize_group_commit(
        empty_group,
        decision,
        evaluations=(evaluation,),
        cycle_at=operational_at,
        committed_at=operational_at,
        alarm_configuration_revision=session_a.alarm_configuration_revision,
        tool_registry_revision=session_a.tool_registry_revision,
        runtime_artifact_version='1.0.0',
    )
    assert seed is not None
    assert runtime_a.composition.commit_batch(context_a, (seed,)).record_count == 1
    before_snapshot = persistence.read_snapshot('mill-feed')
    assert before_snapshot is not None
    assert len(persistence.read_durable_records()) == 1

    projection.record = _record('alarm-r11', is_active=False)
    _write_qualification(
        evidence_file, revision='alarm-r11', qualified_at='2026-09-27T12:03:00+00:00'
    )
    result_b = _publish(materialization, volume, run_id='materialization-b')
    assert result_b.outcome is AlarmMaterializationOutcome.READY
    published_b = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    assert published_b is not None
    assert published_b.result_id == result_b.result_id != result_a.result_id
    assert published_b.runtime.defined_alarm_identities == (_IDENTITY,)
    assert published_b.runtime.planned_alarms == ()
    assert published_b.delivery.alarms[0].is_active is False

    context_a._begin_iteration(2)
    assert runtime_a.iteration(context_a).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    )
    assert executions_a[-1] is session_a
    assert persistence.read_effective_head() == effective_a
    assert persistence.read_snapshot('mill-feed') == before_snapshot
    assert len(persistence.read_durable_adoptions()) == 1

    runtime_b, context_b, executions_b = _runtime_job(volume, run_id='runtime-b')
    runtime_b.iteration_executor.clock = lambda: _AT + timedelta(seconds=2)
    result = runtime_b.iteration(context_b)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert result.cycle_executed is True
    assert executions_b[0].alarm_configuration_revision == 'alarm-r11'
    assert executions_b[0].entries == ()

    adopted = runtime_b.composition.durability.persistence
    head = adopted.read_effective_head()
    assert head.target_artifact_ref.result_id == published_b.result_id
    assert head.target_artifact_ref.manifest_sha256 == published_b.manifest_sha256
    assert adopted.read_head().aligned
    adoptions = adopted.read_durable_adoptions()
    assert len(adoptions) == 2
    v2 = adoptions[-1].record
    assert type(v2) is ConfigurationAdoptionRecordV2
    assert tuple(ref.priority_group for ref in v2.group_commits) == ('mill-feed',)
    durable_groups = adopted.read_durable_records()
    assert len(durable_groups) == 2
    assert durable_groups[-1].record.commit.priority_group == 'mill-feed'
    assert durable_groups[-1].record.record_hash == v2.group_commits[0].record_hash
    after_snapshot = adopted.read_snapshot('mill-feed')
    assert after_snapshot is not None
    assert after_snapshot.last_commit_id == v2.group_commits[0].commit_id
    restored_group = runtime_b.composition.load_group('mill-feed', planned_alarms=())
    assert restored_group.state.episode is None
    assert all(alarm.occurrence is None for alarm in restored_group.state.alarms)

    restarted, new_context, new_executions = _runtime_job(volume, run_id='runtime-c')
    assert restarted.iteration(new_context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    )
    assert new_executions[0].entries == ()
    replayed = restarted.composition.durability.persistence
    assert replayed.read_effective_head() == head
    assert replayed.read_snapshot('mill-feed') == after_snapshot
    assert len(replayed.read_durable_adoptions()) == 2


@dataclass(frozen=True, slots=True)
class _ControlledFrame:
    value: float

    @property
    def dataframe(self):
        return ({'value': self.value},)

    def last_row(self):
        return {'value': self.value}

    def last_value(self, column: str, default=None):
        return self.value if column == 'value' else default

    def last_value_number(self, column: str, default: float | None = None) -> float | None:
        return self.value if column == 'value' else default


@dataclass(frozen=True, slots=True)
class _ControlledIterationData:
    as_of: datetime
    plan: DataLoadPlan
    value: float | None

    def data_for(self, identity: AlarmIdentity) -> DataRuntimeContext:
        assert identity == _IDENTITY
        assert self.value is not None
        assert len(self.plan.views) == 1
        return DataRuntimeContext(frames={self.plan.views[0].view: _ControlledFrame(self.value)})


@dataclass(slots=True)
class _ControlledSourceLoader:
    values: list[float]
    loads: list[tuple[DataLoadPlan, datetime]]

    def load(self, *, plan: DataLoadPlan, as_of: datetime) -> _ControlledIterationData:
        self.loads.append((plan, as_of))
        assert len(plan.views) in (0, 1)
        if plan.views:
            assert plan.views[0].source is DataSource.PI_INTERPOLATED
            assert plan.views[0].partition is DataPartition.LATEST
            return _ControlledIterationData(as_of, plan, self.values.pop(0))
        return _ControlledIterationData(as_of, plan, None)


def _threshold_from_loaded_frame(evaluation_context: EvaluationContext) -> AlarmEvaluation:
    frame = evaluation_context.data.get(DataSource.PI_INTERPOLATED, DataPartition.LATEST)
    value = frame.last_value_number('value')
    assert value is not None
    status = (
        AlarmStatus.ACTIVE
        if value > evaluation_context.parameters['limit']
        else AlarmStatus.INACTIVE
    )
    return AlarmEvaluation(
        alarm_identity=evaluation_context.alarm_identity,
        status=status,
        evaluated_at=evaluation_context.now,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='threshold', contract_version='v1', payload={'value': value}
        ),
    )


def _operational_runtime_job(
    volume: Path,
    *,
    source_loader: _ControlledSourceLoader,
    iteration_times: tuple[datetime, ...],
    adoption_at: datetime,
    run_id: str,
):
    composition = build_alarm_runtime_composition(
        runtime_configuration=_runtime_configuration(volume)
    )
    requirement = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn(name='value', data_type=DataColumnType.FLOAT),),
    )
    evaluator_registry = AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=_threshold_from_loaded_frame,
                requirements=(requirement,),
            ),
        )
    )
    results: list[AlarmOperationalCycleResult] = []
    time_source = iter(iteration_times)
    pinned_cycle: AlarmOperationalCycle | None = None
    pinned_loader: AlarmIterationLoader | None = None

    def run_cycle(context: JobRuntimeContext, session: AlarmExecutionSession) -> None:
        nonlocal pinned_cycle, pinned_loader
        if pinned_cycle is None:
            pinned_loader = AlarmIterationLoader(session=session, source_loader=source_loader)
            pinned_cycle = AlarmOperationalCycle(
                session=session,
                composition=composition,
                occurrence_id_factory=lambda identity, at: (
                    f'{identity.alarm_key}-{at:%Y%m%dT%H%M%S}'
                ),
                episode_id_factory=lambda group, at: f'{group}-{at:%Y%m%dT%H%M%S}',
                commit_time_provider=_CommitClock(),
                runtime_artifact_version='1.0.0',
                technical_evidence_contract=EvidenceContractRef(
                    contract_key='controlled-integration', contract_version='v1'
                ),
            )
        assert pinned_cycle.session is session
        assert pinned_loader is not None
        iteration = pinned_loader.load(as_of=next(time_source))
        assert iteration.session is session
        results.append(pinned_cycle.execute(context, iteration))

    configured = AlarmConfiguredIterationExecutor(
        reader=RuntimeLocalConfigurationReader(volume_path=volume, source_key=_SOURCE.value),
        evaluator_registry=evaluator_registry,
        adoption_executor=AlarmConfigurationAdoptionExecutor(
            composition=composition,
            commit_time_provider=_CommitClock(),
            runtime_artifact_version='1.0.0',
        ),
        run_cycle=run_cycle,
        clock=lambda: adoption_at,
        adoption_id_factory=lambda: (
            f'adoption-{len(composition.durability.persistence.read_durable_adoptions()) + 1}'
        ),
    )
    job = AlarmRuntimeJobComposition(composition=composition, iteration_executor=configured)
    context = _context(volume, service_name='alarms-runtime', run_id=run_id)
    job.recover(context)
    return job, context, results


def test_real_materialization_drives_repeated_operational_cycles_and_next_job_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    published_a = _publish(materialization, volume, run_id='materialization-a')
    assert published_a.outcome is AlarmMaterializationOutcome.READY

    source_a = _ControlledSourceLoader(values=[12.0, 8.0, 13.0], loads=[])
    runtime_a, context_a, cycles_a = _operational_runtime_job(
        volume,
        source_loader=source_a,
        iteration_times=(
            _AT + timedelta(seconds=1),
            _AT + timedelta(seconds=6),
            _AT + timedelta(seconds=11),
        ),
        adoption_at=_AT,
        run_id='runtime-a',
    )
    first = runtime_a.iteration(context_a)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert first.cycle_executed is True
    assert cycles_a[-1].evaluations[0].status is AlarmStatus.ACTIVE
    session_a = cycles_a[-1].iteration.session
    assert session_a.alarm_configuration_revision == 'alarm-r10'
    assert len(session_a.data_plan.views) == 1
    persistence = runtime_a.composition.durability.persistence
    effective_a = persistence.read_effective_head()
    assert len(persistence.read_durable_records()) == 1
    assert persistence.read_snapshot('mill-feed') is not None
    assert cycles_a[-1].commit_result is not None
    assert cycles_a[-1].commit_result.record_count == 1

    context_a._begin_iteration(2)
    second = runtime_a.iteration(context_a)
    assert second.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert cycles_a[-1].evaluations[0].status is AlarmStatus.INACTIVE
    assert cycles_a[-1].iteration.session is session_a
    assert len(persistence.read_durable_records()) == 2
    assert (
        runtime_a.composition.load_group(
            'mill-feed', planned_alarms=session_a.planned_alarms
        ).state.episode
        is None
    )

    projection.record = _record('alarm-r11', is_active=False)
    _write_qualification(
        evidence_file, revision='alarm-r11', qualified_at='2026-09-27T12:03:00+00:00'
    )
    published_b = _publish(materialization, volume, run_id='materialization-b')
    assert published_b.outcome is AlarmMaterializationOutcome.READY
    assert published_b.result_id != published_a.result_id

    def forbidden(*args, **kwargs):
        pytest.fail('operational cycles must not reread runtime configuration')

    with monkeypatch.context() as patch:
        patch.setattr(RuntimeLocalConfigurationReader, 'load_ready_candidate', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'load_effective_revision', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'assert_current_effective', forbidden)
        context_a._begin_iteration(3)
        third = runtime_a.iteration(context_a)
    assert third.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert cycles_a[-1].evaluations[0].status is AlarmStatus.ACTIVE
    assert cycles_a[-1].iteration.session is session_a
    assert len(persistence.read_durable_records()) == 3
    assert persistence.read_effective_head() == effective_a
    assert len(persistence.read_durable_adoptions()) == 1
    assert len(source_a.loads) == 3
    assert tuple(timestamp for _, timestamp in source_a.loads) == (
        _AT + timedelta(seconds=1),
        _AT + timedelta(seconds=6),
        _AT + timedelta(seconds=11),
    )
    assert all(plan is session_a.data_plan for plan, _ in source_a.loads)

    source_b = _ControlledSourceLoader(values=[], loads=[])
    runtime_b, context_b, cycles_b = _operational_runtime_job(
        volume,
        source_loader=source_b,
        iteration_times=(_AT + timedelta(seconds=21),),
        adoption_at=_AT + timedelta(seconds=20),
        run_id='runtime-b',
    )
    adopted = runtime_b.iteration(context_b)
    assert adopted.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert adopted.cycle_executed is True
    assert cycles_b[0].iteration.session.alarm_configuration_revision == 'alarm-r11'
    assert cycles_b[0].iteration.session.entries == ()
    assert cycles_b[0].evaluations == ()
    assert cycles_b[0].commit_result is None
    assert len(source_b.loads) == 1
    assert source_b.loads[0][0].views == ()
    durable = runtime_b.composition.durability.persistence
    assert durable.read_effective_head().target_artifact_ref.result_id == published_b.result_id
    assert durable.read_head().aligned
    assert len(durable.read_durable_adoptions()) == 2
    adoption = durable.read_durable_adoptions()[-1].record
    assert type(adoption) is ConfigurationAdoptionRecordV2
    assert tuple(group.priority_group for group in adoption.group_commits) == ('mill-feed',)
    assert len(durable.read_durable_records()) == 4
    assert durable.read_snapshot('mill-feed').last_commit_id == adoption.group_commits[0].commit_id
    assert runtime_b.composition.load_group('mill-feed', planned_alarms=()).state.episode is None

    (materialization_root(volume) / 'ready.json').unlink()
    source_c = _ControlledSourceLoader(values=[], loads=[])
    recovered, recovered_context, recovered_cycles = _operational_runtime_job(
        volume,
        source_loader=source_c,
        iteration_times=(_AT + timedelta(seconds=25),),
        adoption_at=_AT + timedelta(seconds=24),
        run_id='runtime-c',
    )
    resumed = recovered.iteration(recovered_context)
    assert resumed.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert resumed.cycle_executed is True
    assert recovered_cycles[0].iteration.session.entries == ()
    assert recovered.composition.durability.persistence.read_effective_head() == (
        durable.read_effective_head()
    )
    assert len(recovered.composition.durability.persistence.read_durable_adoptions()) == 2


def _structural_ready_after_active_cycle(tmp_path: Path) -> tuple[Path, str]:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    published_a = _publish(materialization, volume, run_id='materialization-a')
    assert published_a.outcome is AlarmMaterializationOutcome.READY

    runtime_a, context_a, cycles_a = _operational_runtime_job(
        volume,
        source_loader=_ControlledSourceLoader(values=[12.0], loads=[]),
        iteration_times=(_AT + timedelta(seconds=1),),
        adoption_at=_AT,
        run_id='runtime-a',
    )
    assert runtime_a.iteration(context_a).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    )
    assert cycles_a[0].evaluations[0].status is AlarmStatus.ACTIVE
    original = runtime_a.composition.durability.persistence
    assert len(original.read_durable_adoptions()) == 1
    assert len(original.read_durable_records()) == 1
    assert original.read_snapshot('mill-feed') is not None
    assert (
        runtime_a.composition.load_group(
            'mill-feed', planned_alarms=cycles_a[0].iteration.session.planned_alarms
        ).state.episode
        is not None
    )

    candidate_b = _record('alarm-r11')
    candidate_rule = replace(candidate_b.payload.configuration.rules[0], criticality=Criticality.C2)
    projection.record = replace(
        candidate_b,
        payload=replace(
            candidate_b.payload,
            configuration=replace(candidate_b.payload.configuration, rules=(candidate_rule,)),
        ),
    )
    _write_qualification(
        evidence_file, revision='alarm-r11', qualified_at='2026-09-27T12:03:00+00:00'
    )
    published_b = _publish(materialization, volume, run_id='materialization-b')
    assert published_b.outcome is AlarmMaterializationOutcome.READY
    assert published_b.result_id != published_a.result_id
    ready = _reader(volume).read_published_ready(source_key=_SOURCE.value)
    assert ready is not None
    assert ready.result_id == published_b.result_id
    assert len(ready.runtime.planned_alarms) == 1
    assert ready.runtime.planned_alarms[0].criticality is Criticality.C2
    return volume, published_b.result_id


def test_v2_same_second_conflict_is_explicit_and_next_iteration_keeps_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20)
    source_b = _ControlledSourceLoader(values=[14.0, 15.0], loads=[])
    runtime_b, context_b, cycles_b = _operational_runtime_job(
        volume,
        source_loader=source_b,
        iteration_times=(adoption_at, adoption_at + timedelta(seconds=1)),
        adoption_at=adoption_at,
        run_id='runtime-b',
    )
    with pytest.raises(
        AlarmOperationalCycleError,
        match='priority group already has a durable commit for iteration as_of',
    ):
        runtime_b.iteration(context_b)

    persistence = runtime_b.composition.durability.persistence
    assert persistence.read_head().aligned
    assert persistence.read_effective_head().target_artifact_ref.result_id == published_b
    assert len(persistence.read_durable_adoptions()) == 2
    adoption = persistence.read_durable_adoptions()[-1].record
    assert type(adoption) is ConfigurationAdoptionRecordV2
    assert tuple(ref.priority_group for ref in adoption.group_commits) == ('mill-feed',)
    assert len(persistence.read_durable_records()) == 2
    assert persistence.read_snapshot('mill-feed').last_commit_id == (
        adoption.group_commits[0].commit_id
    )
    assert cycles_b == []
    assert len(source_b.loads) == 1
    assert source_b.loads[0][1] == adoption_at

    def forbidden(*args, **kwargs):
        pytest.fail('A pinned job must not reopen configuration readers on the next cycle')

    context_b._begin_iteration(2)
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeLocalConfigurationReader, 'load_ready_candidate', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'load_effective_revision', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'assert_current_effective', forbidden)
        subsequent = runtime_b.iteration(context_b)

    assert subsequent.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert subsequent.cycle_executed is True
    assert cycles_b[0].iteration.session.alarm_configuration_revision == 'alarm-r11'
    assert cycles_b[0].evaluations[0].status is AlarmStatus.ACTIVE
    assert cycles_b[0].commit_result is not None
    assert len(source_b.loads) == 2
    assert source_b.loads[0][0] is source_b.loads[1][0]
    assert source_b.loads[1][1] == adoption_at + timedelta(seconds=1)
    assert len(persistence.read_durable_adoptions()) == 2
    assert len(persistence.read_durable_records()) == 3
    assert persistence.read_snapshot('mill-feed').last_commit_id != (
        adoption.group_commits[0].commit_id
    )


def test_v2_first_operational_cycle_one_second_later_does_not_collide(
    tmp_path: Path,
) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20)
    operational_at = adoption_at + timedelta(seconds=1)
    source_b = _ControlledSourceLoader(values=[14.0], loads=[])
    runtime_b, context_b, cycles_b = _operational_runtime_job(
        volume,
        source_loader=source_b,
        iteration_times=(operational_at,),
        adoption_at=adoption_at,
        run_id='runtime-b',
    )
    first = runtime_b.iteration(context_b)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert first.cycle_executed is True
    assert len(cycles_b) == 1
    assert cycles_b[0].evaluations[0].status is AlarmStatus.ACTIVE
    assert cycles_b[0].commit_result is not None
    assert len(source_b.loads) == 1
    assert source_b.loads[0][1] == operational_at

    persistence = runtime_b.composition.durability.persistence
    assert persistence.read_head().aligned
    assert persistence.read_effective_head().target_artifact_ref.result_id == published_b
    assert len(persistence.read_durable_adoptions()) == 2
    adoption = persistence.read_durable_adoptions()[-1].record
    assert type(adoption) is ConfigurationAdoptionRecordV2
    assert tuple(ref.priority_group for ref in adoption.group_commits) == ('mill-feed',)
    assert len(persistence.read_durable_records()) == 3
    persisted_at = persistence.read_durable_records()[-1].record.commit.evaluated_at
    assert datetime.fromisoformat(persisted_at) == operational_at
    assert persistence.read_snapshot('mill-feed').last_commit_id != (
        adoption.group_commits[0].commit_id
    )
    assert (
        runtime_b.composition.load_group(
            'mill-feed', planned_alarms=cycles_b[0].iteration.session.planned_alarms
        ).state.episode
        is not None
    )


def _coordinated_runtime_job(
    volume: Path,
    *,
    source_loader: _ControlledSourceLoader,
    iteration_times: tuple[datetime, ...],
    adoption_at: datetime,
    run_id: str,
):
    composition = build_alarm_runtime_composition(
        runtime_configuration=_runtime_configuration(volume)
    )
    requirement = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn(name='value', data_type=DataColumnType.FLOAT),),
    )
    registry = AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=_threshold_from_loaded_frame,
                requirements=(requirement,),
            ),
        )
    )

    def cycle_factory(session: AlarmExecutionSession) -> AlarmOperationalCycle:
        return AlarmOperationalCycle(
            session=session,
            composition=composition,
            occurrence_id_factory=lambda identity, at: f'{identity.alarm_key}-{at:%Y%m%dT%H%M%S}',
            episode_id_factory=lambda group, at: f'{group}-{at:%Y%m%dT%H%M%S}',
            commit_time_provider=_CommitClock(),
            runtime_artifact_version='1.0.0',
            technical_evidence_contract=EvidenceContractRef(
                contract_key='controlled-integration', contract_version='v1'
            ),
        )

    clock = iter(iteration_times)
    runner = AlarmOperationalCycleRunner(
        composition=composition,
        source_loader=source_loader,
        cycle_factory=cycle_factory,
        clock=lambda: next(clock),
    )
    configured = AlarmConfiguredIterationExecutor(
        reader=RuntimeLocalConfigurationReader(volume_path=volume, source_key=_SOURCE.value),
        evaluator_registry=registry,
        adoption_executor=AlarmConfigurationAdoptionExecutor(
            composition=composition,
            commit_time_provider=_CommitClock(),
            runtime_artifact_version='1.0.0',
        ),
        run_cycle=runner,
        clock=lambda: adoption_at,
        adoption_id_factory=lambda: (
            f'adoption-{len(composition.durability.persistence.read_durable_adoptions()) + 1}'
        ),
    )
    job = AlarmRuntimeJobComposition(composition=composition, iteration_executor=configured)
    context = _context(volume, service_name='alarms-runtime', run_id=run_id)
    job.recover(context)
    return job, context


def test_v2_same_second_runner_defers_before_consuming_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20)
    source = _ControlledSourceLoader(values=[14.0], loads=[])
    runtime, context = _coordinated_runtime_job(
        volume,
        source_loader=source,
        iteration_times=(adoption_at, adoption_at + timedelta(seconds=1)),
        adoption_at=adoption_at,
        run_id='runtime-b-coordinated',
    )
    first = runtime.iteration(context)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert first.cycle_executed is False
    assert context._next_iteration_delay() == 1.0
    assert source.loads == []
    persistence = runtime.composition.durability.persistence
    assert persistence.read_effective_head().target_artifact_ref.result_id == published_b
    assert len(persistence.read_durable_adoptions()) == 2
    assert len(persistence.read_durable_records()) == 2

    def forbidden(*args, **kwargs):
        pytest.fail('pinned runner must not reopen configuration after temporal defer')

    context._begin_iteration(2)
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeLocalConfigurationReader, 'load_ready_candidate', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'load_effective_revision', forbidden)
        patch.setattr(RuntimeLocalConfigurationReader, 'assert_current_effective', forbidden)
        second = runtime.iteration(context)
    assert second.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert second.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert len(source.loads) == 1
    assert source.loads[0][1] == adoption_at + timedelta(seconds=1)
    assert len(persistence.read_durable_records()) == 3
    assert persistence.read_snapshot('mill-feed').last_commit_id != (
        persistence.read_durable_adoptions()[-1].record.group_commits[0].commit_id
    )


def test_two_operational_cycles_same_second_defer_second_before_data_load(
    tmp_path: Path,
) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    evidence_file = tmp_path / 'qualification.json'
    projection = _ControlledProjection(_record('alarm-r10'))
    _write_qualification(
        evidence_file, revision='alarm-r10', qualified_at='2026-09-27T12:02:00+00:00'
    )
    materialization = _materialization_job(
        volume=volume, projection=projection, qualification_file=evidence_file
    )
    assert _publish(materialization, volume, run_id='materialization-a').outcome is (
        AlarmMaterializationOutcome.READY
    )
    first_at = _AT + timedelta(seconds=1)
    source = _ControlledSourceLoader(values=[12.0, 8.0], loads=[])
    runtime, context = _coordinated_runtime_job(
        volume,
        source_loader=source,
        iteration_times=(first_at, first_at, first_at + timedelta(seconds=1)),
        adoption_at=_AT,
        run_id='runtime-a-coordinated',
    )
    assert runtime.iteration(context).adoption_outcome is (
        AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    )
    assert len(source.loads) == 1
    assert len(runtime.composition.durability.persistence.read_durable_records()) == 1

    context._begin_iteration(2)
    deferred = runtime.iteration(context)
    assert deferred.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert deferred.cycle_executed is False
    assert context._next_iteration_delay() == 1.0
    assert len(source.loads) == 1
    assert len(runtime.composition.durability.persistence.read_durable_records()) == 1

    context._begin_iteration(3)
    final = runtime.iteration(context)
    assert final.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert len(source.loads) == 2
    assert source.loads[-1][1] == first_at + timedelta(seconds=1)
    persistence = runtime.composition.durability.persistence
    assert len(persistence.read_durable_records()) == 2
    snapshot = persistence.read_snapshot('mill-feed')
    assert snapshot is not None
    assert snapshot.as_document().get('episode') is None


def test_runner_keeps_first_cycle_immediate_when_second_is_distinct(tmp_path: Path) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20)
    operational_at = adoption_at + timedelta(seconds=1)
    source = _ControlledSourceLoader(values=[14.0], loads=[])
    runtime, context = _coordinated_runtime_job(
        volume,
        source_loader=source,
        iteration_times=(operational_at,),
        adoption_at=adoption_at,
        run_id='runtime-b-coordinated',
    )
    first = runtime.iteration(context)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert first.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert len(source.loads) == 1
    persistence = runtime.composition.durability.persistence
    assert persistence.read_effective_head().target_artifact_ref.result_id == published_b
    assert len(persistence.read_durable_records()) == 3


def test_fractional_v2_adoption_blocks_only_until_next_utc_second(tmp_path: Path) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20, milliseconds=500)
    sampled_at = _AT + timedelta(seconds=20, milliseconds=750)
    source = _ControlledSourceLoader(values=[14.0], loads=[])
    runtime, context = _coordinated_runtime_job(
        volume,
        source_loader=source,
        iteration_times=(sampled_at, _AT + timedelta(seconds=21)),
        adoption_at=adoption_at,
        run_id='runtime-b-fractional-adoption',
    )
    first = runtime.iteration(context)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert first.cycle_executed is False
    assert context._next_iteration_delay() == 0.25
    assert source.loads == []
    assert (
        runtime.composition.durability.persistence.read_effective_head().target_artifact_ref.result_id
        == (published_b)
    )

    context._begin_iteration(2)
    assert runtime.iteration(context).cycle_executed is True
    assert len(source.loads) == 1
    assert source.loads[0][1] == _AT + timedelta(seconds=21)
    assert len(runtime.composition.durability.persistence.read_durable_records()) == 3


def test_runner_wait_is_remaining_fraction_not_fixed_one_second(tmp_path: Path) -> None:
    volume, published_b = _structural_ready_after_active_cycle(tmp_path)
    adoption_at = _AT + timedelta(seconds=20)
    sampled_at = adoption_at + timedelta(milliseconds=750)
    source = _ControlledSourceLoader(values=[14.0], loads=[])
    runtime, context = _coordinated_runtime_job(
        volume,
        source_loader=source,
        iteration_times=(sampled_at, adoption_at + timedelta(seconds=1)),
        adoption_at=adoption_at,
        run_id='runtime-b-fractional',
    )
    first = runtime.iteration(context)
    assert first.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert first.cycle_executed is False
    assert context._next_iteration_delay() == 0.25
    assert source.loads == []
    assert (
        runtime.composition.durability.persistence.read_effective_head().target_artifact_ref.result_id
        == (published_b)
    )

    context._begin_iteration(2)
    assert runtime.iteration(context).cycle_executed is True
    assert len(source.loads) == 1
    assert source.loads[0][1] == adoption_at + timedelta(seconds=1)
    assert len(runtime.composition.durability.persistence.read_durable_records()) == 3
