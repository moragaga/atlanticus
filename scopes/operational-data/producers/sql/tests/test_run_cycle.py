from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from atlanticus.data_producers.sql import (
    SqlDataProducerError,
    SqlDataProducerJob,
    SqlDataProducerPlanner,
    SqlExecutionPlan,
    SqlProducerState,
    SqlSourceExecutionResult,
    SqlSourcePlan,
    SqlSourceState,
)
from atlanticus.runtime import RuntimeCancellationRequested


class _Planner(SqlDataProducerPlanner):
    def __init__(self, *plans):
        self.plans = plans
        self.calls = 0

    def capture(self, definitions, *, captured_at_utc=None, context=None):
        plan = self.plans[min(self.calls, len(self.plans) - 1)]
        self.calls += 1
        return plan


class _State(SqlProducerState):
    def __init__(self):
        self.values = {}

    def source_state(self, source_key):
        return self.values.get(source_key, SqlSourceState(source_key=source_key))

    def commit_source(self, **values):
        previous = self.source_state(values['source_key'])
        state = SqlSourceState(
            source_key=values['source_key'],
            revision=previous.revision + (1 if values['changed'] else 0),
            source_scope_token=values['target_scope_token'],
            publication_signatures=values['publication_signatures'],
        )
        self.values[values['source_key']] = state
        return state


class _Executor:
    def __init__(self, *, results=None, errors=None):
        self.results = {} if results is None else dict(results)
        self.errors = {} if errors is None else dict(errors)
        self.calls = []

    def execute(self, *, plan, context):
        source_key = plan.definition.source_key
        self.calls.append(source_key)
        error = self.errors.get(source_key)
        if error is not None:
            raise error
        return self.results[source_key]


class _Logger:
    def exception(self, *args, **kwargs):
        return None


class _Context:
    def __init__(self, *, poll_seconds=7.5, cancel_on_check=None):
        self.memory = {}
        self.execution = {}
        self.iteration = {}
        self.work = False
        self.delay = None
        self.definition = SimpleNamespace(sleep_seconds=poll_seconds)
        self.logger = _Logger()
        self.cancel_on_check = cancel_on_check
        self.cancel_checks = 0

    def raise_if_cancelled(self):
        self.cancel_checks += 1
        if self.cancel_on_check == self.cancel_checks:
            raise RuntimeCancellationRequested('requested')

    def get_memory(self, key, default=None):
        return self.memory.get(key, default)

    def set_memory(self, key, value):
        self.memory[key] = value

    def get_execution_fact(self, key, default=None):
        return self.execution.get(key, default)

    def set_execution_fact(self, key, value):
        self.execution[key] = value

    def increment_execution_counter(self, key, amount=1):
        self.execution[key] = self.execution.get(key, 0) + amount

    def set_iteration_fact(self, key, value):
        self.iteration[key] = value

    def mark_iteration_work(self):
        self.work = True

    def set_next_iteration_delay(self, seconds):
        self.delay = seconds


def _source(definition, key):
    definition = replace(definition, source_key=key, source_table=f'dbo.{key}')
    return SqlSourcePlan(definition=definition)


def _result(source):
    return SqlSourceExecutionResult(
        source_key=source.definition.source_key,
        source_row_count=0,
        publications=(),
    )


def _job(snapshot_definition, planner, executor) -> SqlDataProducerJob:
    return SqlDataProducerJob(
        producer_key='producer',
        definitions=(snapshot_definition,),
        planner=planner,
        producer_state=_State(),
        executor=executor,
    )


def test_run_cycle_consumes_all_sources(snapshot_definition) -> None:
    first = _source(snapshot_definition, 'source_first')
    second = _source(snapshot_definition, 'source_second')
    plan = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(first, second),
    )
    executor = _Executor(
        results={
            first.definition.source_key: _result(first),
            second.definition.source_key: _result(second),
        }
    )
    context = _Context(poll_seconds=9.0)
    job = _job(snapshot_definition, _Planner(plan), executor)

    job.run_cycle(context)

    assert executor.calls == ['source_first', 'source_second']
    assert context.cancel_checks == 2
    assert context.execution['cycles_completed'] == 1
    assert context.delay == 9.0


def test_run_cycle_stops_before_starting_next_cycle(snapshot_definition) -> None:
    first = _source(snapshot_definition, 'source_first')
    second = _source(snapshot_definition, 'source_second')
    planner = _Planner(
        SqlExecutionPlan(datetime(2026, 10, 2, 12, 0, tzinfo=UTC), (first,)),
        SqlExecutionPlan(datetime(2026, 10, 2, 12, 1, tzinfo=UTC), (second,)),
    )
    executor = _Executor(
        results={
            first.definition.source_key: _result(first),
            second.definition.source_key: _result(second),
        }
    )
    job = _job(snapshot_definition, planner, executor)

    job.run_cycle(_Context())

    assert planner.calls == 1
    assert executor.calls == ['source_first']


def test_run_cycle_propagates_cycle_failure(snapshot_definition) -> None:
    source = _source(snapshot_definition, 'source_failed')
    plan = SqlExecutionPlan(datetime(2026, 10, 2, 12, 0, tzinfo=UTC), (source,))
    context = _Context()
    job = _job(
        snapshot_definition,
        _Planner(plan),
        _Executor(errors={'source_failed': ValueError('source failure')}),
    )

    with pytest.raises(SqlDataProducerError, match='1 source failure'):
        job.run_cycle(context)

    assert context.execution['cycles_completed'] == 0


def test_run_cycle_checks_cancellation_between_sources(snapshot_definition) -> None:
    first = _source(snapshot_definition, 'source_first')
    second = _source(snapshot_definition, 'source_second')
    plan = SqlExecutionPlan(datetime(2026, 10, 2, 12, 0, tzinfo=UTC), (first, second))
    executor = _Executor(
        results={
            first.definition.source_key: _result(first),
            second.definition.source_key: _result(second),
        }
    )
    context = _Context(cancel_on_check=2)
    job = _job(snapshot_definition, _Planner(plan), executor)

    with pytest.raises(RuntimeCancellationRequested, match='requested'):
        job.run_cycle(context)

    assert executor.calls == ['source_first']
    assert context.memory['producer.execution_cursor'] == 1
