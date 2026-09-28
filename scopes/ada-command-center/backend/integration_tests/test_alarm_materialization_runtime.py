from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent

from ada_command_center.alarms.materialization import (
    LocalAlarmMaterializationReader,
    materialization_root,
)
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
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobComposition,
    RuntimeLocalConfigurationReader,
    build_alarm_runtime_composition,
)
from atlanticus.kernel import Environment
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


def _rule() -> AlarmDefinition:
    return AlarmDefinition(
        identity=_IDENTITY,
        rule_name='risk-rule',
        display_name='Risk',
        title='Risk alarm',
        cause_template='Value exceeds threshold',
        is_active=True,
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


def _record(revision: str) -> ProjectionRecord:
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
            configuration=AlarmConfiguration(rules=(_rule(),), messages=()),
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
