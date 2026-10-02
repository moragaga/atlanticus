from datetime import UTC, datetime

import pytest

from atlanticus.connectivity.sql import SqlTableChangeMarker
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
    def __init__(self, plan):
        self.plan = plan

    def capture(self, definitions, *, context=None):
        return self.plan


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
            source_change_marker=values['target_change_marker'],
            source_scope_token=values['target_scope_token'],
            publication_signatures=values['publication_signatures'],
        )
        self.values[values['source_key']] = state
        return state


class _Executor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def execute(self, *, plan, context):
        if self.error is not None:
            raise self.error
        return self.result


class _Logger:
    def exception(self, *args, **kwargs):
        return None


class _Context:
    def __init__(self):
        self.memory = {}
        self.execution = {}
        self.iteration = {}
        self.work = False
        self.delay = None
        self.completed = False
        self.logger = _Logger()

    def get_or_create(self, key, factory):
        if key not in self.memory:
            self.memory[key] = factory()
        return self.memory[key]

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

    def complete_execution(self):
        self.completed = True


def _job(snapshot_definition, plan, executor) -> SqlDataProducerJob:
    return SqlDataProducerJob(
        producer_key='producer',
        definitions=(snapshot_definition,),
        planner=_Planner(plan),
        producer_state=_State(),
        executor=executor,
    )


def test_empty_plan_completes_without_artificial_delay(snapshot_definition) -> None:
    plan = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(),
    )
    context = _Context()
    job = _job(snapshot_definition, plan, _Executor())

    job.run_iteration(context)

    assert context.completed is True
    assert context.delay is None
    assert context.execution['sources_planned'] == 0
    assert context.iteration == {'outcome': 'skipped', 'reason': 'no_source_change'}


def test_last_source_completes_execution(snapshot_definition) -> None:
    source = SqlSourcePlan(
        definition=snapshot_definition,
        change_marker=SqlTableChangeMarker(
            source_table=snapshot_definition.source_table,
            generation_token='generation',
            last_user_update_token='target',
            user_updates=1,
        ),
    )
    plan = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(source,),
    )
    result = SqlSourceExecutionResult(
        source_key=snapshot_definition.source_key,
        source_row_count=0,
        publications=(),
    )
    context = _Context()
    job = _job(snapshot_definition, plan, _Executor(result=result))

    job.run_iteration(context)

    assert context.completed is True
    assert context.delay is None
    assert context.execution['sources_processed'] == 1


def test_last_source_failure_does_not_complete_execution(snapshot_definition) -> None:
    source = SqlSourcePlan(
        definition=snapshot_definition,
        change_marker=SqlTableChangeMarker(
            source_table=snapshot_definition.source_table,
            generation_token='generation',
            last_user_update_token='target',
            user_updates=1,
        ),
    )
    plan = SqlExecutionPlan(
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sources=(source,),
    )
    context = _Context()
    job = _job(snapshot_definition, plan, _Executor(error=ValueError('source failure')))

    with pytest.raises(SqlDataProducerError, match='1 source failure'):
        job.run_iteration(context)

    assert context.completed is False
