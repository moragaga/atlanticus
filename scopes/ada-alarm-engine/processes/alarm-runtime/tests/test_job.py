from __future__ import annotations

from datetime import UTC, datetime

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvidenceSnapshot,
)
from ada.alarms.persistence import AlarmMaterializationPersistenceError
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycleResult,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmRuntimeConfigurationOutcome,
    AlarmRuntimeJob,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
)
from atlanticus.operational_data.sources import DataSourceApplications

from .support import engine_configuration, registry

CYCLE_AT = datetime(2026, 10, 7, 20, 15, tzinfo=UTC)


class Reader:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def read_published_engine(self, *, source_key: str):
        assert source_key == 'alarm-configuration'
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


class Cycle:
    def __init__(self) -> None:
        self.sessions = []

    def run(self, session):
        self.sessions.append(session)
        identity = session.entries[0].identity
        return AlarmEvaluationCycleResult(
            cycle_at=CYCLE_AT,
            evaluations=(
                AlarmEvaluation(
                    alarm_identity=identity,
                    status=AlarmStatus.INACTIVE,
                    evaluated_at=CYCLE_AT,
                    evidence_snapshot=EvidenceSnapshot(
                        contract_key='test',
                        contract_version='1',
                        payload={},
                    ),
                ),
            ),
        )


class Context:
    def __init__(self) -> None:
        self.memory = {}
        self.facts = {}
        self.delay = None
        self.work = False

    def raise_if_cancelled(self) -> None:
        return None

    def get_memory(self, key):
        return self.memory.get(key)

    def set_memory(self, key, value) -> None:
        self.memory[key] = value

    def set_next_iteration_delay(self, value) -> None:
        self.delay = value

    def mark_iteration_work(self) -> None:
        self.work = True

    def set_iteration_fact(self, key, value) -> None:
        self.facts[key] = value


def _job(reader, *, evaluator_registry=None, applications=None, cycle=None):
    return AlarmRuntimeJob(
        reader=reader,
        source_key='alarm-configuration',
        evaluator_registry=registry() if evaluator_registry is None else evaluator_registry,
        source_applications=(
            DataSourceApplications(pi='pi-app') if applications is None else applications
        ),
        cycle=Cycle() if cycle is None else cycle,
    )


def test_initial_iteration_waits_when_no_ready_engine_exists() -> None:
    context = Context()
    cycle = Cycle()
    result = _job(Reader([None]), cycle=cycle).run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.WAITING
    assert result.session is None
    assert result.cycle is None
    assert context.delay == 30.0
    assert context.work is False
    assert cycle.sessions == []


def test_runtime_executes_cycle_again_when_configuration_is_unchanged() -> None:
    configuration = engine_configuration()
    context = Context()
    cycle = Cycle()
    job = _job(Reader([configuration, configuration]), cycle=cycle)

    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)

    assert first.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert second.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert second.session is first.session
    assert first.cycle is not None
    assert second.cycle is not None
    assert cycle.sessions == [first.session, first.session]
    assert context.work is True


def test_runtime_adopts_new_executable_resolution_and_runs_it_immediately() -> None:
    first_configuration = engine_configuration()
    second_configuration = engine_configuration(release='ALARMS-8', limit=12.0)
    context = Context()
    cycle = Cycle()
    job = _job(Reader([first_configuration, second_configuration]), cycle=cycle)

    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)

    assert first.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert second.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert second.session is not first.session
    assert second.session.configuration == second_configuration
    assert cycle.sessions[-1] is second.session
    assert context.work is True


def test_unexecutable_new_ready_keeps_pinned_session_and_engine_cycle() -> None:
    context = Context()
    cycle = Cycle()
    job = _job(
        Reader(
            [
                engine_configuration(),
                engine_configuration(release='ALARMS-8', evaluator_key='missing'),
            ]
        ),
        cycle=cycle,
    )

    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)

    assert second.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert second.session is not first.session
    assert second.session.unregistered_alarms == (second.session.entries[0].identity,)
    assert cycle.sessions[-1] is second.session
    assert context.work is True


def test_invalid_published_engine_keeps_pinned_session_and_engine_cycle() -> None:
    context = Context()
    cycle = Cycle()
    job = _job(
        Reader(
            [
                engine_configuration(),
                AlarmMaterializationPersistenceError('corrupt READY'),
            ]
        ),
        cycle=cycle,
    )

    first = job.run_iteration(context)
    second = job.run_iteration(context)

    assert second.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert second.session is first.session
    assert second.reason == 'published_engine_invalid_using_pinned'
    assert cycle.sessions[-1] is first.session


def test_missing_new_ready_keeps_pinned_session_and_engine_cycle() -> None:
    context = Context()
    cycle = Cycle()
    job = _job(Reader([engine_configuration(), None]), cycle=cycle)

    first = job.run_iteration(context)
    second = job.run_iteration(context)

    assert second.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert second.session is first.session
    assert second.reason == 'published_engine_missing_using_pinned'
    assert cycle.sessions[-1] is first.session


def test_initial_unexecutable_ready_does_not_create_session() -> None:
    context = Context()
    cycle = Cycle()
    result = _job(
        Reader([engine_configuration(evaluator_key='missing')]),
        evaluator_registry=AlarmEvaluatorRegistry(contracts=()),
        cycle=cycle,
    ).run_iteration(context)

    assert result.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert result.session is not None
    assert result.session.unregistered_alarms == (result.session.entries[0].identity,)
    assert result.session.entries[0].contract_available is False
    assert context.work is True
    assert cycle.sessions == [result.session]


def test_ready_requiring_unconfigured_source_route_is_not_adopted() -> None:
    context = Context()
    cycle = Cycle()
    dispatch_registry = AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=registry().contracts[0].evaluator,
                inputs=(
                    DataInputSpec(
                        input_key='truck',
                        source=DataSource.DISPATCH_STD_TRUCK,
                        view=DataView.LATEST,
                        columns=(DataColumn('truck', DataColumnType.TEXT),),
                    ),
                ),
            ),
        )
    )

    result = _job(
        Reader([engine_configuration()]),
        evaluator_registry=dispatch_registry,
        applications=DataSourceApplications(pi='pi-app'),
        cycle=cycle,
    ).run_iteration(context)

    assert result.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert result.session is None
    assert result.cycle is None
    assert context.delay == 30.0
    assert cycle.sessions == []


def test_iteration_records_cycle_summary() -> None:
    context = Context()
    result = _job(Reader([engine_configuration()])).run_iteration(context)

    assert context.facts['cycle_at_utc'] == CYCLE_AT.isoformat()
    assert context.facts['evaluation_count'] == 1
    assert context.facts['active_evaluation_count'] == 0
    assert context.facts['inactive_evaluation_count'] == 1
    assert context.facts['error_evaluation_count'] == 0
    assert result.cycle is not None
