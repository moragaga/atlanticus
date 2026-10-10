from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from atlanticus.runtime import JobDefinition, execute_job
from atlanticus.runtime.errors import RuntimeContractError


def _definition():
    return JobDefinition(
        module_name='test_alarm_logging',
        service_name='alarm-logging-test',
        run_once=True,
        execution_timeout_seconds=10,
        shutdown_grace_seconds=2,
        iteration_timeout_seconds=5,
        lease_timeout_seconds=12,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
        iteration_summary_every=0,
    )


def _run(tmp_path, *, report):
    def iteration(context):
        context.mark_iteration_work()
        context.increment_execution_counter('evaluated', 1)
        if report:
            context.request_iteration_summary()
            context.set_iteration_fact('reason', 'significant_change')

    execute_job(
        definition=_definition(),
        iteration=iteration,
        argv=[],
        environ={'ENVIRONMENT': 'local', 'APPLICATION': 'ada', 'VOLUMEN_PATH': str(tmp_path)},
    )
    day = datetime.now(UTC).date().isoformat()
    root = tmp_path / 'ada' / 'logs' / 'alarm-logging-test' / f'day={day}'
    return root


def test_quiet_work_is_counted_without_persisting_iteration_summary(tmp_path):
    directory = _run(tmp_path, report=False)
    assert not (directory / 'iterations.jsonl').exists()
    completed = json.loads((directory / 'executions.jsonl').read_text().splitlines()[-1])
    assert completed['work_iterations'] == 1
    assert completed['empty_iterations'] == 0
    assert completed['evaluated'] == 1


def test_requested_summary_is_emitted_while_work_remains_counted(tmp_path):
    directory = _run(tmp_path, report=True)
    completed = json.loads((directory / 'executions.jsonl').read_text().splitlines()[-1])
    iterations = [
        json.loads(line) for line in (directory / 'iterations.jsonl').read_text().splitlines()
    ]
    assert completed['work_iterations'] == 1
    assert len(iterations) == 1
    assert iterations[0]['reason'] == 'significant_change'


def test_default_job_definition_keeps_existing_iteration_log_behavior():
    assert (
        JobDefinition(
            module_name='test_alarm_logging', service_name='sample'
        ).iteration_summary_every
        == 1
    )


@pytest.mark.parametrize('value', [True, False, -1, 1.2, '0'])
def test_invalid_iteration_summary_every_is_rejected(value):
    with pytest.raises((TypeError, RuntimeContractError)):
        replace(_definition(), iteration_summary_every=value)
