from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from ada.contracts.alarms import AlarmIdentity

from ada_command_center.alarms.materialization.local_reader import (
    materialization_result_id,
    materialization_root,
)
from ada_command_center.alarms.persistence import AlarmRecoveryRequiredError
from ada_command_center.processes.alarms_runtime import (
    AlarmConfigurationAdoptionExecutor,
    AlarmConfiguredIterationExecutor,
    AlarmEvaluatorRegistry,
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobComposition,
    RuntimeLocalConfigurationReader,
    build_alarm_runtime_composition,
)
from atlanticus.kernel import Environment
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration

AT = datetime(2026, 9, 27, 20, 0, tzinfo=UTC)
SOURCE = 'alarm-configuration'


def _write(path: Path, document: dict) -> tuple[str, int]:
    content = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha256(content).hexdigest(), len(content)


def _publish(volume: Path, *, qualification: str = 'b') -> str:
    root = materialization_root(volume)
    projection_digest = 'a' * 64
    qualification_digest = qualification * 64
    result_id = materialization_result_id(
        source_key=SOURCE,
        projection_digest=projection_digest,
        qualification_digest=qualification_digest,
    )
    resolution = {
        'alarm_configuration_revision': 'R10',
        'confirmed_tool_catalog_revision': 'C5',
    }
    runtime = {
        'resolution_key': resolution,
        'defined_alarm_identities': [],
        'planned_alarms': [],
        'parameters_by_alarm': [],
    }
    delivery = {'resolution_key': resolution, 'alarms': []}
    version = root / 'versions' / result_id
    inventory = {}
    for label, payload in (('runtime', runtime), ('delivery', delivery)):
        digest, size = _write(version / f'{label}.json', payload)
        inventory[label] = {
            'path': f'{label}.json',
            'sha256': digest,
            'size_bytes': size,
        }
    manifest = {
        'document_type': 'ada_command_center_alarm_materialization_result',
        'schema_version': 1,
        'source_key': SOURCE,
        'result_id': result_id,
        'status': 'READY',
        'resolution_key': resolution,
        'provenance': {
            'source_release_id': 'R10',
            'source_published_at_utc': '2026-09-26T12:00:00+00:00',
            'confirmed_tool_catalog_revision': 'C5',
            'projection_digest': projection_digest,
            'qualification_digest': qualification_digest,
            'qualification_producer': 'controlled-test',
            'qualification_evidence_ref': 'qualification-1',
            'qualified_at_utc': '2026-09-26T12:01:00+00:00',
        },
        'findings': [],
        'artifacts': inventory,
    }
    manifest_hash, _ = _write(version / 'manifest.json', manifest)
    _write(
        root / 'ready.json',
        {
            'document_type': 'ada_command_center_alarm_materialization_ready',
            'schema_version': 1,
            'source_key': SOURCE,
            'result_id': result_id,
            'resolution_key': resolution,
            'manifest_sha256': manifest_hash,
        },
    )
    return result_id


class _Clock:
    def committed_at(self, *, cycle_at: datetime) -> datetime:
        return cycle_at


def _compose(volume: Path, cycle=None):
    configuration = RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=volume,
    )
    composition = build_alarm_runtime_composition(runtime_configuration=configuration)
    adoption = AlarmConfigurationAdoptionExecutor(
        composition=composition,
        commit_time_provider=_Clock(),
        runtime_artifact_version='1.0.0',
    )
    runs = []

    def recording_cycle(context, session):
        runs.append(session)

    if cycle is None:
        cycle = recording_cycle
    orchestrator = AlarmConfiguredIterationExecutor(
        reader=RuntimeLocalConfigurationReader(volume_path=volume, source_key=SOURCE),
        evaluator_registry=AlarmEvaluatorRegistry(contracts=()),
        adoption_executor=adoption,
        run_cycle=cycle,
        clock=lambda: AT,
        adoption_id_factory=lambda: (
            f'adoption-{len(composition.durability.persistence.read_durable_adoptions()) + 1}'
        ),
    )
    job = AlarmRuntimeJobComposition(composition=composition, iteration_executor=orchestrator)
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name='ada_command_center.processes.alarms_runtime',
            service_name='alarms-runtime',
        ),
        configuration=configuration,
        run_id='run-1',
        correlation_id='correlation-1',
        wall_clock=lambda: AT,
    )

    @contextmanager
    def fence():
        yield

    context._bind_lease_authority(generation=1, checker=lambda: None, fence=fence)
    job.recover(context)
    return job, context, runs


def test_initial_absence_waits_thirty_seconds_without_writing_or_running(tmp_path):
    job, context, runs = _compose(tmp_path)
    result = job.iteration(context)
    persistence = job.composition.durability.persistence
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert result.cycle_executed is False
    assert context._next_iteration_delay() == 30.0
    assert context.get_iteration_fact('alarm_configuration_status') == 'waiting_for_ready'
    assert persistence.read_durable_adoptions() == ()
    assert runs == []


def test_new_ready_bootstraps_and_runs_immediately_on_first_iteration(tmp_path):
    published = _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    result = job.iteration(context)
    persistence = job.composition.durability.persistence
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert result.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert persistence.read_effective_head().target_artifact_ref.result_id == published
    assert len(persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1


def test_waiting_job_starts_as_soon_as_ready_appears(tmp_path):
    job, context, runs = _compose(tmp_path)
    assert job.iteration(context).cycle_executed is False
    context._begin_iteration(2)
    _publish(tmp_path)
    result = job.iteration(context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert context._next_iteration_delay() is None
    assert len(runs) == 1


def test_restart_uses_exact_effective_without_published_ready(tmp_path):
    _publish(tmp_path)
    original, first, _ = _compose(tmp_path)
    assert original.iteration(first).adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    (materialization_root(tmp_path) / 'ready.json').unlink()
    restarted, context, runs = _compose(tmp_path)
    result = restarted.iteration(context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert result.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert len(runs) == 1
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1


def test_new_ready_is_adopted_only_by_next_job(tmp_path):
    original = _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    assert job.iteration(context).adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    first_session = runs[0]
    new_ready = _publish(tmp_path, qualification='c')

    context._begin_iteration(2)
    result = job.iteration(context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert result.cycle_executed is True
    assert context._next_iteration_delay() is None
    persistence = job.composition.durability.persistence
    assert persistence.read_effective_head().target_artifact_ref.result_id == original
    assert len(persistence.read_durable_adoptions()) == 1
    assert len(runs) == 2
    assert runs[1] is first_session

    restarted, new_context, new_runs = _compose(tmp_path)
    result = restarted.iteration(new_context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
    assert result.cycle_executed is True
    assert new_context._next_iteration_delay() is None
    persistence = restarted.composition.durability.persistence
    assert persistence.read_effective_head().target_artifact_ref.result_id == new_ready
    assert len(persistence.read_durable_adoptions()) == 2
    assert len(new_runs) == 1
    new_context._begin_iteration(2)
    assert (
        restarted.iteration(new_context).adoption_outcome
        is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    )
    assert new_runs[1] is new_runs[0]
    assert len(persistence.read_durable_adoptions()) == 2


def test_pinned_job_does_not_reopen_configuration_readers(tmp_path, monkeypatch):
    original = _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    job.iteration(context)
    first_session = runs[0]
    _publish(tmp_path, qualification='c')

    def unexpected_lookup(*args, **kwargs):
        raise AssertionError('configuration must not be reread during an active job')

    monkeypatch.setattr(
        RuntimeLocalConfigurationReader, 'load_effective_revision', unexpected_lookup
    )
    monkeypatch.setattr(RuntimeLocalConfigurationReader, 'load_ready_candidate', unexpected_lookup)
    monkeypatch.setattr(
        RuntimeLocalConfigurationReader, 'assert_current_effective', unexpected_lookup
    )
    for number in (2, 3):
        context._begin_iteration(number)
        result = job.iteration(context)
        assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
        assert result.cycle_executed is True
        assert runs[-1] is first_session
    persistence = job.composition.durability.persistence
    assert persistence.read_effective_head().target_artifact_ref.result_id == original
    assert len(persistence.read_durable_adoptions()) == 1


def test_rejected_candidate_preserves_effective_on_next_job(tmp_path, monkeypatch):
    original = _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    job.iteration(context)
    _publish(tmp_path, qualification='c')
    rejection = SimpleNamespace(
        identity=AlarmIdentity(family_key='mill', alarm_key='risk'),
        rejection_reason=SimpleNamespace(value='priority_group_changed'),
    )
    monkeypatch.setattr(
        'ada_command_center.processes.alarms_runtime.configured_iteration.plan_configuration_adoption',
        lambda source, target: SimpleNamespace(
            is_adoptable=False,
            rejected_changes=(rejection,),
        ),
    )
    restarted, new_context, new_runs = _compose(tmp_path)
    result = restarted.iteration(new_context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.REJECTED
    assert result.cycle_executed is True
    assert (
        restarted.composition.durability.persistence.read_effective_head().target_artifact_ref.result_id
        == original
    )
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1
    assert len(new_runs) == 1


def test_invalid_initial_ready_waits_without_logging_repeatedly_and_can_bootstrap(
    tmp_path, monkeypatch
):
    published = _publish(tmp_path)
    root = materialization_root(tmp_path)
    pointer = json.loads((root / 'ready.json').read_text())
    original_digest = pointer['manifest_sha256']
    pointer['manifest_sha256'] = '0' * 64
    _write(root / 'ready.json', pointer)
    job, context, runs = _compose(tmp_path)
    warnings = []
    monkeypatch.setattr(
        context.logger, 'warning', lambda message, **kwargs: warnings.append(message)
    )
    persistence = job.composition.durability.persistence
    for iteration in (1, 2):
        if iteration > 1:
            context._begin_iteration(iteration)
        result = job.iteration(context)
        assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
        assert result.cycle_executed is False
        assert context._next_iteration_delay() == 30.0
        assert context.get_iteration_fact('alarm_configuration_status') == 'waiting_for_valid_ready'
        assert persistence.read_effective_head() is None
        assert persistence.read_durable_adoptions() == ()
        assert runs == []
    assert len(warnings) == 1

    pointer['manifest_sha256'] = original_digest
    _write(root / 'ready.json', pointer)
    context._begin_iteration(3)
    result = job.iteration(context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert result.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert persistence.read_effective_head().target_artifact_ref.result_id == published
    assert len(persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1

    pointer['manifest_sha256'] = '0' * 64
    _write(root / 'ready.json', pointer)
    restarted, new_context, new_runs = _compose(tmp_path)
    result = restarted.iteration(new_context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.REJECTED
    assert result.cycle_executed is True
    assert new_context._next_iteration_delay() is None
    assert len(new_runs) == 1
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1


def test_unexecutable_initial_ready_waits_until_new_ready_is_published(tmp_path, monkeypatch):
    import ada_command_center.processes.alarms_runtime.configured_iteration as module

    unexecutable = _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    actual_builder = module.build_alarm_configuration_revision

    def build_candidate(*, candidate, evaluator_registry):
        if candidate.result_id == unexecutable:
            raise ValueError('Required evaluator contract is unavailable')
        return actual_builder(candidate=candidate, evaluator_registry=evaluator_registry)

    monkeypatch.setattr(module, 'build_alarm_configuration_revision', build_candidate)
    warnings = []
    monkeypatch.setattr(
        context.logger, 'warning', lambda message, **kwargs: warnings.append(message)
    )
    persistence = job.composition.durability.persistence
    for iteration in (1, 2):
        if iteration > 1:
            context._begin_iteration(iteration)
        result = job.iteration(context)
        assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
        assert result.cycle_executed is False
        assert context._next_iteration_delay() == 30.0
        assert (
            context.get_iteration_fact('alarm_configuration_status')
            == 'waiting_for_executable_ready'
        )
        assert persistence.read_effective_head() is None
        assert persistence.read_durable_adoptions() == ()
        assert runs == []
    assert len(warnings) == 1

    valid = _publish(tmp_path, qualification='c')
    context._begin_iteration(3)
    result = job.iteration(context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    assert result.cycle_executed is True
    assert context._next_iteration_delay() is None
    assert persistence.read_effective_head().target_artifact_ref.result_id == valid
    assert len(persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1


def test_initial_ready_reader_error_does_not_hide_durable_effective_corruption(tmp_path):
    _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    assert job.iteration(context).adoption_outcome is AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
    restarted, new_context, new_runs = _compose(tmp_path)
    pointer = materialization_root(tmp_path) / 'ready.json'
    pointer.write_text('{invalid-json')
    effective_path = tmp_path / 'ada-command-center' / 'alarms' / 'runtime' / 'state'
    (effective_path / 'effective-head.json').unlink()
    with pytest.raises(AlarmRecoveryRequiredError):
        restarted.iteration(new_context)
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1
    assert new_runs == []


def test_new_job_fails_closed_if_effective_projection_disappears_after_recovery(tmp_path):
    _publish(tmp_path)
    job, context, runs = _compose(tmp_path)
    job.iteration(context)
    restarted, new_context, new_runs = _compose(tmp_path)
    root = tmp_path / 'ada-command-center' / 'alarms' / 'runtime' / 'state'
    (root / 'effective-head.json').unlink()
    with pytest.raises(AlarmRecoveryRequiredError):
        restarted.iteration(new_context)
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1
    assert len(runs) == 1
    assert new_runs == []


def test_crash_during_cycle_after_bootstrap_does_not_duplicate_adoption(tmp_path):
    _publish(tmp_path)

    def failed_cycle(context, session):
        raise RuntimeError('source unavailable')

    job, context, _ = _compose(tmp_path, cycle=failed_cycle)
    with pytest.raises(RuntimeError, match='source unavailable'):
        job.iteration(context)
    assert len(job.composition.durability.persistence.read_durable_adoptions()) == 1
    restarted, new_context, runs = _compose(tmp_path)
    result = restarted.iteration(new_context)
    assert result.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED
    assert result.cycle_executed is True
    assert len(runs) == 1
    assert len(restarted.composition.durability.persistence.read_durable_adoptions()) == 1
