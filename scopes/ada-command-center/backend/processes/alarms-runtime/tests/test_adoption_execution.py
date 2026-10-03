from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality

from ada_command_center.alarms.core import (
    AlarmEvaluation,
    AlarmResolutionKey,
    AlarmRouting,
    AlarmRuntimeState,
    AlarmStatus,
    DeactivationEffect,
    EvidenceSnapshot,
    GroupLifecycleState,
    PlannedAlarm,
    materialize_group_commit,
    reduce_group_cycle,
)
from ada_command_center.alarms.materialization import AlarmConfigurationArtifactRef
from ada_command_center.alarms.persistence import (
    AlarmPersistence,
    AlarmPersistenceConflictError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
)
from ada_command_center.processes.alarms_runtime import (
    AlarmConfigurationAdoptionExecutor,
    AlarmConfigurationRevision,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmRuntimeGroup,
    ConfigurationAdoptionExecutionError,
    build_alarm_execution_session,
    build_alarm_runtime_composition,
    plan_configuration_adoption,
)
from ada_command_center.processes.alarms_runtime.commit import compose_engine_commit_record
from atlanticus.kernel import Environment
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration

AT = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def _identity(name):
    return AlarmIdentity(family_key='family', alarm_key=name)


def _revision(letter, *, defined=(), executable=(), orders=None, groups=None):
    resolution_key = AlarmResolutionKey('R10', 'C5')
    ref = AlarmConfigurationArtifactRef(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + sha256(letter.encode()).hexdigest(),
        manifest_sha256='f' * 64,
        resolution_key=resolution_key,
    )
    orders = {} if orders is None else orders
    groups = {} if groups is None else groups
    plans = tuple(
        PlannedAlarm(
            identity=_identity(name),
            kind=AlarmKind.RISK,
            criticality=Criticality.C3,
            priority_group=groups.get(name, 'group-a'),
            priority_order=orders.get(name, index + 1),
            evaluator_key='threshold',
            alarm_configuration_revision='R10',
            tool_registry_revision='C5',
            routing=AlarmRouting(origin_tool_key='tool-a'),
        )
        for index, name in enumerate(executable)
    )
    session = build_alarm_execution_session(
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        planned_alarms=plans,
        evaluator_registry=AlarmEvaluatorRegistry(
            contracts=(
                AlarmEvaluatorContract(
                    family_key='family',
                    evaluator_key='threshold',
                    evaluator=lambda context: None,
                ),
            ),
        ),
    )
    return AlarmConfigurationRevision(
        artifact_ref=ref,
        defined_alarm_identities=tuple(_identity(name) for name in defined),
        session=session,
    )


class _Clock:
    def committed_at(self, *, cycle_at):
        return cycle_at


def _executor(tmp_path):
    configuration = RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=tmp_path,
    )
    composition = build_alarm_runtime_composition(runtime_configuration=configuration)
    return AlarmConfigurationAdoptionExecutor(
        composition=composition,
        commit_time_provider=_Clock(),
        runtime_artifact_version='1.0.0',
    )


def _context(executor):
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name='ada_command_center.processes.alarms_runtime',
            service_name='alarms-runtime',
        ),
        configuration=executor.composition.runtime_configuration,
        run_id='run-1',
        correlation_id='correlation-1',
        wall_clock=lambda: AT,
    )

    @contextmanager
    def fence():
        yield

    context._bind_lease_authority(generation=1, checker=lambda: None, fence=fence)
    return context


@pytest.mark.parametrize(
    ('source', 'target', 'expected_groups'),
    (
        ({'defined': ()}, {'defined': ('new',), 'executable': ('new',)}, ('group-a',)),
        ({'defined': ()}, {'defined': ('new',)}, ()),
        ({'defined': ('old',)}, {'defined': ('old',), 'executable': ('old',)}, ('group-a',)),
        ({'defined': ('old',)}, {'defined': ()}, ()),
        ({'defined': ('old',), 'executable': ('old',)}, {'defined': ()}, ('group-a',)),
    ),
)
def test_prepare_supports_definition_transitions_without_writing(
    tmp_path, source, target, expected_groups
):
    executor = _executor(tmp_path)
    plan = plan_configuration_adoption(_revision('a', **source), _revision('b', **target))

    groups = executor.prepare(plan, effective_at=AT)

    assert tuple(group.priority_group for group in groups) == expected_groups
    assert executor.composition.durability.persistence.read_head().durable is None
    assert executor.composition.durability.persistence.list_snapshots() == ()
    assert executor.composition.durability.persistence.read_effective_head() is None


def test_prepare_coalesces_changes_per_group_and_keeps_source_groups(tmp_path):
    executor = _executor(tmp_path)
    source = _revision(
        'a',
        defined=('disabled', 'removed'),
        executable=('removed',),
        groups={'removed': 'group-a'},
    )
    target = _revision(
        'b',
        defined=('disabled', 'new'),
        executable=('disabled', 'new'),
        groups={'disabled': 'group-b', 'new': 'group-b'},
    )
    plan = plan_configuration_adoption(source, target)

    groups = executor.prepare(plan, effective_at=AT)

    assert tuple(group.priority_group for group in groups) == ('group-a', 'group-b')
    assert all(group.materialization is None for group in groups)


def test_prepare_preserves_local_deactivation_when_rule_is_enabled(tmp_path, monkeypatch):
    executor = _executor(tmp_path)
    source = _revision('a', defined=('old',))
    target = _revision('b', defined=('old',), executable=('old',))
    effect = DeactivationEffect(
        effect_id='effect-1',
        source_occurrence_id='occurrence-1',
        effective_from=AT - timedelta(minutes=1),
        effective_until=AT + timedelta(hours=1),
    )
    state = GroupLifecycleState(
        priority_group='group-a',
        alarms=(AlarmRuntimeState(alarm_identity=_identity('old'), deactivation_effect=effect),),
    )

    def load_group(self, priority_group, *, planned_alarms):
        assert priority_group == 'group-a'
        assert planned_alarms == ()
        return AlarmRuntimeGroup(state=state, snapshot=None)

    monkeypatch.setattr(type(executor.composition), 'load_group', load_group)
    groups = executor.prepare(plan_configuration_adoption(source, target), effective_at=AT)

    assert len(groups) == 1
    assert groups[0].decision.state.get(_identity('old')).deactivation_effect == effect
    assert executor.composition.durability.persistence.read_head().durable is None


def test_prepare_keeps_compatible_priority_reconciliation(tmp_path):
    executor = _executor(tmp_path)
    source = _revision('a', defined=('old',), executable=('old',))
    target = _revision('b', defined=('old',), executable=('old',), orders={'old': 2})

    groups = executor.prepare(plan_configuration_adoption(source, target), effective_at=AT)

    assert tuple(group.priority_group for group in groups) == ('group-a',)
    assert executor.composition.durability.persistence.read_head().durable is None


def test_prepare_rejects_executable_group_migration(tmp_path):
    executor = _executor(tmp_path)
    source = _revision('a', defined=('old',), executable=('old',))
    target = _revision(
        'b',
        defined=('old',),
        executable=('old',),
        groups={'old': 'group-b'},
    )
    with pytest.raises(ConfigurationAdoptionExecutionError, match='plan is rejected'):
        executor.prepare(plan_configuration_adoption(source, target), effective_at=AT)


def test_bootstrap_v1_pins_ready_without_synthetic_groups(tmp_path):
    executor = _executor(tmp_path)
    target = _revision('a', defined=('old',), executable=('old',))
    context = _context(executor)

    result = executor.bootstrap(context, target, effective_at=AT, adoption_id='first')

    persistence = executor.composition.durability.persistence
    assert result.record_count == 1
    assert persistence.list_snapshots() == ()
    assert persistence.read_durable_records() == ()
    (adoption,) = tuple(entry.record for entry in persistence.read_durable_adoptions())
    assert type(adoption) is ConfigurationAdoptionRecord
    assert adoption.previous_artifact_ref is None
    assert adoption.target_artifact_ref.result_id == target.artifact_ref.result_id
    assert persistence.read_effective_head().adoption_id == 'first'

    with pytest.raises(ConfigurationAdoptionExecutionError, match='absence of an EFFECTIVE'):
        executor.bootstrap(context, target, effective_at=AT, adoption_id='retry')
    assert len(persistence.read_durable_adoptions()) == 1


def test_execute_v1_records_metadata_only_change_after_bootstrap(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('old',))
    target = _revision('b', defined=('old', 'new'))
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')

    result = executor.execute(
        context,
        plan_configuration_adoption(source, target),
        effective_at=AT + timedelta(seconds=2),
        adoption_id='second',
    )

    persistence = executor.composition.durability.persistence
    assert result.groups == ()
    assert result.materializations == ()
    assert result.commit_result.record_count == 1
    assert type(result.adoption_record) is ConfigurationAdoptionRecord
    assert persistence.read_effective_head().target_artifact_ref.result_id == (
        target.artifact_ref.result_id
    )
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (
        persistence.read_durable_adoptions()[0].record,
        result.adoption_record,
    )
    assert persistence.read_durable_records() == ()


def test_execute_requires_current_exact_effective_and_no_legacy_commit(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('old',))
    target = _revision('b', defined=('old',), executable=('old',))
    plan = plan_configuration_adoption(source, target)
    with pytest.raises(ConfigurationAdoptionExecutionError, match='initial configuration'):
        executor.execute(context, plan, effective_at=AT, adoption_id='not-bootstrap')
    assert executor.composition.durability.persistence.read_head().durable is None
    executor.bootstrap(context, target, effective_at=AT, adoption_id='first')
    with pytest.raises(ConfigurationAdoptionExecutionError, match='does not match'):
        executor.execute(context, plan, effective_at=AT + timedelta(seconds=2), adoption_id='stale')
    assert len(executor.composition.durability.persistence.read_durable_adoptions()) == 1


def test_execute_v1_supports_added_enabled_and_removed_without_group_state(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('removed', 'enabled'))
    target = _revision(
        'b',
        defined=('enabled', 'added'),
        executable=('enabled', 'added'),
    )
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')

    result = executor.execute(
        context,
        plan_configuration_adoption(source, target),
        effective_at=AT + timedelta(seconds=2),
        adoption_id='second',
    )
    assert tuple(group.priority_group for group in result.groups) == ('group-a',)
    assert result.materializations == ()
    assert result.commit_result.record_count == 1
    assert type(result.adoption_record) is ConfigurationAdoptionRecord
    assert executor.composition.durability.persistence.list_snapshots() == ()


def test_execute_v1_pins_delivery_only_artifact_without_group_commits(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('old',), executable=('old',))
    target = _revision('b', defined=('old',), executable=('old',))
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')

    result = executor.execute(
        context,
        plan_configuration_adoption(source, target),
        effective_at=AT + timedelta(seconds=2),
        adoption_id='delivery-only',
    )
    assert result.groups == ()
    assert result.commit_result.record_count == 1
    assert type(result.adoption_record) is ConfigurationAdoptionRecord
    assert executor.composition.durability.persistence.read_effective_head().adoption_id == (
        'delivery-only'
    )


def test_execute_rejected_plan_does_not_change_effective(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('old',), executable=('old',))
    target = _revision(
        'b',
        defined=('old',),
        executable=('old',),
        groups={'old': 'group-b'},
    )
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')
    with pytest.raises(ConfigurationAdoptionExecutionError, match='plan is rejected'):
        executor.execute(
            context,
            plan_configuration_adoption(source, target),
            effective_at=AT + timedelta(seconds=2),
            adoption_id='rejected',
        )
    persistence = executor.composition.durability.persistence
    assert persistence.read_effective_head().adoption_id == 'first'
    assert len(persistence.read_durable_adoptions()) == 1
    assert persistence.read_durable_records() == ()


def _seed_open_occurrences(executor, context, source, *, at):
    persistence = executor.composition.durability.persistence
    group_records = []
    for entry in source.session.entries:
        plan = entry.planned_alarm
        previous = GroupLifecycleState(priority_group=plan.priority_group)
        evaluation = AlarmEvaluation(
            alarm_identity=plan.identity,
            status=AlarmStatus.ACTIVE,
            evaluated_at=at,
            evidence_snapshot=EvidenceSnapshot(
                contract_key='threshold',
                contract_version='v1',
                payload={'value': 10.0},
            ),
        )
        decision = reduce_group_cycle(
            previous,
            cycle_at=at,
            planned_alarms=(plan,),
            evaluations=(evaluation,),
            occurrence_id_factory=lambda identity, when: f'O-{identity.alarm_key}',
            episode_id_factory=lambda group, when: f'E-{group}',
        )
        materialization = materialize_group_commit(
            previous,
            decision,
            evaluations=(evaluation,),
            cycle_at=at,
            committed_at=at,
            alarm_configuration_revision=source.alarm_configuration_revision,
            tool_registry_revision=source.tool_registry_revision,
            runtime_artifact_version='1.0.0',
        )
        assert materialization is not None
        group_records.append(compose_engine_commit_record(materialization, previous_snapshot=None))
    persistence.commit_batch(
        tuple(group_records),
        assert_authority=context.assert_lease_current,
        fenced_mutation=context.fenced_mutation,
    )


def test_execute_v2_atomically_closes_two_groups_and_updates_effective(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision(
        'a',
        defined=('one', 'two'),
        executable=('one', 'two'),
        groups={'one': 'group-a', 'two': 'group-b'},
    )
    target = _revision('b', defined=('one', 'two'))
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')
    _seed_open_occurrences(executor, context, source, at=AT + timedelta(seconds=1))

    result = executor.execute(
        context,
        plan_configuration_adoption(source, target),
        effective_at=AT + timedelta(seconds=2),
        adoption_id='second',
    )

    persistence = executor.composition.durability.persistence
    assert tuple(group.priority_group for group in result.groups) == (
        'group-a',
        'group-b',
    )
    assert len(result.materializations) == 2
    assert type(result.adoption_record) is ConfigurationAdoptionRecordV2
    assert tuple(ref.priority_group for ref in result.adoption_record.group_commits) == (
        'group-a',
        'group-b',
    )
    assert result.commit_result.record_count == 3
    assert persistence.read_effective_head().target_artifact_ref.result_id == (
        target.artifact_ref.result_id
    )
    assert len(persistence.read_durable_adoptions()) == 2
    assert all(
        'episode' not in persistence.read_snapshot(group).as_document()
        for group in ('group-a', 'group-b')
    )
    restarted = AlarmPersistence(shared_volume_path=tmp_path)
    assert restarted.read_effective_head() == persistence.read_effective_head()


def test_v2_crash_replays_all_groups_before_exposing_new_effective(tmp_path, monkeypatch):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision(
        'a',
        defined=('one', 'two'),
        executable=('one', 'two'),
        groups={'one': 'group-a', 'two': 'group-b'},
    )
    target = _revision('b', defined=('one', 'two'))
    executor.bootstrap(context, source, effective_at=AT, adoption_id='first')
    _seed_open_occurrences(executor, context, source, at=AT + timedelta(seconds=1))
    persistence = executor.composition.durability.persistence
    original = persistence._materialize_entry
    calls = 0

    def fail_second(entry):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('simulated second-group crash')
        return original(entry)

    monkeypatch.setattr(persistence, '_materialize_entry', fail_second)
    with pytest.raises(RuntimeError, match='simulated second-group crash'):
        executor.execute(
            context,
            plan_configuration_adoption(source, target),
            effective_at=AT + timedelta(seconds=2),
            adoption_id='second',
        )
    assert not persistence.read_head().aligned
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.read_effective_head()
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    executor.composition.recover(context)
    assert persistence.read_effective_head().target_artifact_ref.result_id == (
        target.artifact_ref.result_id
    )
    assert len(persistence.read_durable_adoptions()) == 2
    with pytest.raises(ConfigurationAdoptionExecutionError, match='does not match'):
        executor.execute(
            context,
            plan_configuration_adoption(source, target),
            effective_at=AT + timedelta(seconds=3),
            adoption_id='second',
        )
    assert len(persistence.read_durable_adoptions()) == 2


def test_bootstrap_refuses_legacy_group_only_history(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    source = _revision('a', defined=('old',), executable=('old',))
    _seed_open_occurrences(executor, context, source, at=AT + timedelta(seconds=1))

    with pytest.raises(AlarmPersistenceConflictError, match='legacy state migration'):
        executor.bootstrap(
            context,
            source,
            effective_at=AT + timedelta(seconds=2),
            adoption_id='first',
        )
    assert executor.composition.durability.persistence.read_effective_head() is None


def test_crash_after_durable_bootstrap_requires_recovery_without_double_adoption(
    tmp_path, monkeypatch
):
    executor = _executor(tmp_path)
    context = _context(executor)
    persistence = executor.composition.durability.persistence
    original = persistence._materialize_entry
    monkeypatch.setattr(
        persistence,
        '_materialize_entry',
        lambda entry: (_ for _ in ()).throw(RuntimeError('simulated snapshot crash')),
    )
    with pytest.raises(RuntimeError, match='simulated snapshot crash'):
        executor.bootstrap(context, _revision('a'), effective_at=AT, adoption_id='first')
    assert persistence.read_head().durable is not None
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.read_effective_head()
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    executor.composition.recover(context)
    assert persistence.read_effective_head().adoption_id == 'first'
    with pytest.raises(ConfigurationAdoptionExecutionError, match='absence of an EFFECTIVE'):
        executor.bootstrap(context, _revision('a'), effective_at=AT, adoption_id='first')
    assert len(persistence.read_durable_adoptions()) == 1


def test_prepare_fails_when_journal_requires_recovery(tmp_path, monkeypatch):
    executor = _executor(tmp_path)
    persistence = executor.composition.durability.persistence
    monkeypatch.setattr(type(persistence), 'read_head', lambda self: SimpleNamespace(aligned=False))
    plan = plan_configuration_adoption(_revision('a'), _revision('b', defined=('new',)))
    with pytest.raises(ConfigurationAdoptionExecutionError, match='must be recovered'):
        executor.prepare(plan, effective_at=AT)
