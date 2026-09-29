from __future__ import annotations

from pathlib import Path

import pytest

from ada_command_center.processes.alarms_delivery.job import (
    AlarmDeliveryInputJob,
    build_delivery_input_job,
)
from atlanticus.kernel import Environment
from atlanticus.runtime import RuntimeConfiguration


class _Context:
    def __init__(self):
        self.memory = {}
        self.facts = {}

    def assert_lease_current(self):
        return None

    def set_memory(self, key, value):
        self.memory[key] = value

    def get_memory(self, key):
        return self.memory.get(key)

    def set_iteration_fact(self, key, value):
        self.facts[key] = value


def _job(path: Path) -> AlarmDeliveryInputJob:
    configuration = RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=path,
    )
    return build_delivery_input_job(
        runtime_configuration=configuration,
        source_key='alarm-configuration',
        poll_seconds=5,
    )


def test_delivery_job_owns_separate_identity_and_recovery_gate(tmp_path):
    job = _job(tmp_path)
    assert job.definition.service_name == 'alarms-delivery'
    assert job.receiver.engine_root != job.receiver.inbox_root
    context = _Context()
    with pytest.raises(RuntimeError, match='recovery must precede'):
        job.iteration(context)
    job.recover(context)
    result = job.iteration(context)
    assert result.current_status == 'WAITING_EFFECTIVE'
    assert context.facts == {'alarm_delivery_current_status': 'WAITING_EFFECTIVE'}


def test_delivery_job_rejects_invalid_polling(tmp_path):
    configuration = RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=tmp_path,
    )
    with pytest.raises(ValueError, match='positive'):
        build_delivery_input_job(
            runtime_configuration=configuration,
            source_key='alarm-configuration',
            poll_seconds=0,
        )
