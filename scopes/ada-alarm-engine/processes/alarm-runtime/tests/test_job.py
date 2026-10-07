from __future__ import annotations

from ada.alarms.persistence import AlarmMaterializationPersistenceError
from ada.processes.alarm_runtime import (
    AlarmEvaluatorRegistry,
    AlarmRuntimeConfigurationOutcome,
    AlarmRuntimeJob,
)

from .support import engine_configuration, registry


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


def test_initial_iteration_waits_when_no_ready_engine_exists() -> None:
    context = Context()
    result = AlarmRuntimeJob(
        reader=Reader([None]),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
    ).run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.WAITING
    assert result.session is None
    assert context.delay == 30.0
    assert context.work is False


def test_runtime_bootstraps_and_reuses_unchanged_engine_configuration() -> None:
    configuration = engine_configuration()
    context = Context()
    job = AlarmRuntimeJob(
        reader=Reader([configuration, configuration]),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
    )
    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)
    assert first.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert second.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert second.session is first.session
    assert context.work is False


def test_runtime_adopts_new_executable_resolution() -> None:
    first_configuration = engine_configuration()
    second_configuration = engine_configuration(release='ALARMS-8', limit=12.0)
    context = Context()
    job = AlarmRuntimeJob(
        reader=Reader([first_configuration, second_configuration]),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
    )
    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)
    assert first.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert second.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert second.session is not first.session
    assert second.session.configuration == second_configuration
    assert context.work is True


def test_unexecutable_new_ready_keeps_pinned_session() -> None:
    context = Context()
    job = AlarmRuntimeJob(
        reader=Reader(
            [
                engine_configuration(),
                engine_configuration(release='ALARMS-8', evaluator_key='missing'),
            ]
        ),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
    )
    first = job.run_iteration(context)
    context.work = False
    second = job.run_iteration(context)
    assert second.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert second.session is first.session
    assert second.reason == 'published_engine_not_executable'
    assert context.work is False


def test_invalid_published_engine_keeps_pinned_session() -> None:
    context = Context()
    job = AlarmRuntimeJob(
        reader=Reader(
            [
                engine_configuration(),
                AlarmMaterializationPersistenceError('corrupt READY'),
            ]
        ),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
    )
    first = job.run_iteration(context)
    second = job.run_iteration(context)
    assert second.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert second.session is first.session
    assert second.reason == 'published_engine_invalid_using_pinned'


def test_initial_unexecutable_ready_does_not_create_session() -> None:
    context = Context()
    result = AlarmRuntimeJob(
        reader=Reader([engine_configuration(evaluator_key='missing')]),
        source_key='alarm-configuration',
        evaluator_registry=AlarmEvaluatorRegistry(contracts=()),
    ).run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert result.session is None
    assert context.delay == 30.0
