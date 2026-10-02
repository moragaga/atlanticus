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
    def __init__(self, *, results=None, error=None):
        self.results = {} if results is None else dict(results)
        self.error = error
        self.calls = []

    def execute(self, *, plan, context):
        self.calls.append(plan.definition.source_key)
        if self.error is not None:
            raise self.error
        return self.results[plan.definition.source_key]


class _Logger:
    def exception(self, *args, **kwargs):
        return None


class _Context:
    def __init__(self, *, poll_seconds=7.5):
        self.memory = {}
        self.execution = {}
        self.iteration = {}
        self.work = False
        self.delay = None
        self.definition = SimpleNamespace(sleep_seconds=poll_seconds)
        self.logger = _Logger()

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


def test_sources_inside_same_cycle_do_not_wait_for_poll(snapshot_definition) -> None:
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

    job.run_iteration(context)
    assert executor.calls == ['source_first']
    assert context.delay == 0

    context.delay = None
    context.iteration = {}
    job.run_iteration(context)
    assert executor.calls == ['source_first', 'source_second']
    assert context.delay == 9.0
    assert context.execution['cycles_completed'] == 1


def test_empty_cycle_uses_poll_and_explicit_reason(snapshot_definition) -> None:
    empty = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(),
    )
    context = _Context(poll_seconds=6.0)
    job = _job(snapshot_definition, _Planner(empty), _Executor())

    job.run_iteration(context)

    assert context.iteration['reason'] == 'no_sources_planned'
    assert context.delay == 6.0
    assert context.execution['empty_cycles'] == 1


def test_last_source_failure_does_not_close_cycle_as_success(snapshot_definition) -> None:
    source = _source(snapshot_definition, 'source_failed')
    plan = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(source,),
    )
    context = _Context()
    job = _job(snapshot_definition, _Planner(plan), _Executor(error=ValueError('source failure')))

    with pytest.raises(SqlDataProducerError, match='1 source failure'):
        job.run_iteration(context)

    assert context.execution['cycles_completed'] == 0
    assert context.delay is None
