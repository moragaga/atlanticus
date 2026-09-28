from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest

from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    AlarmRuntimeState,
    DeactivationEffect,
    GroupLifecycleState,
    PlannedAlarm,
)
from ada_command_center.alarms.materialization import AlarmConfigurationArtifactRef
from ada_command_center.domain.alarms import AlarmIdentity, AlarmKind, Criticality
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
    return JobRuntimeContext.create(
        definition=JobDefinition(
            module_name='ada_command_center.processes.alarms_runtime',
            service_name='alarms-runtime',
        ),
        configuration=executor.composition.runtime_configuration,
        run_id='run-1',
        correlation_id='correlation-1',
        wall_clock=lambda: AT,
    )


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


def test_execute_never_confirms_group_only_adoption_before_global_integration(tmp_path):
    executor = _executor(tmp_path)
    context = _context(executor)
    cases = (
        (_revision('a'), _revision('b', defined=('new',), executable=('new',))),
        (_revision('c', defined=('old',)), _revision('d', defined=('old',), executable=('old',))),
        (_revision('e', defined=('old',)), _revision('f')),
        (
            _revision('g', defined=('old',), executable=('old',)),
            _revision('h', defined=('old',)),
        ),
        (
            _revision('i', defined=('old',), executable=('old',)),
            _revision('j', defined=('old',), executable=('old',)),
        ),
    )
    for source, target in cases:
        plan = plan_configuration_adoption(source, target)
        with pytest.raises(ConfigurationAdoptionExecutionError, match='global V1/V2'):
            executor.execute(context, plan, effective_at=AT)
    assert executor.composition.durability.persistence.read_head().durable is None


def test_prepare_fails_when_journal_requires_recovery(tmp_path, monkeypatch):
    executor = _executor(tmp_path)
    persistence = executor.composition.durability.persistence
    monkeypatch.setattr(type(persistence), 'read_head', lambda self: SimpleNamespace(aligned=False))
    plan = plan_configuration_adoption(_revision('a'), _revision('b', defined=('new',)))
    with pytest.raises(ConfigurationAdoptionExecutionError, match='must be recovered'):
        executor.prepare(plan, effective_at=AT)
