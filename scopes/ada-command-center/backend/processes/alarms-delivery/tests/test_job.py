from __future__ import annotations

from pathlib import Path

import pytest

from ada_command_center.processes.alarms_delivery.job import (
    AlarmDeliveryJob,
    build_delivery_job,
)
from ada_command_center.processes.alarms_delivery.parallel import (
    CosmosDispatchResult,
    ParallelCosmosPublisher,
)
from ada_command_center.processes.alarms_delivery.receiver import (
    DeliveryInputCycleResult,
    DeliveryProjectionSnapshot,
)
from atlanticus.kernel import Environment
from atlanticus.runtime import JobDefinition, RuntimeConfiguration


def _configuration(path: Path) -> RuntimeConfiguration:
    return RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=path,
    )


def test_delivery_job_waits_for_effective_after_recovery(tmp_path):
    with ParallelCosmosPublisher(
        connections={'tool-a': object()},
        max_workers=1,
        client_factory=lambda _: None,
    ) as publisher:
        job = build_delivery_job(
            runtime_configuration=_configuration(tmp_path),
            source_key='alarm-configuration',
            publisher=publisher,
        )

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

            def mark_iteration_work(self):
                raise AssertionError('waiting iteration must not mark work')

        context = _Context()
        with pytest.raises(RuntimeError, match='recovery must precede'):
            job.iteration(context)
        job.recover(context)
        result = job.iteration(context)
        assert result.current_status == 'WAITING_EFFECTIVE'


def test_delivery_job_marks_work_after_successful_publication():
    class _Receiver:
        def consume(self, _context):
            return DeliveryInputCycleResult(
                current_status='CURRENT_AVAILABLE',
                snapshots=(
                    DeliveryProjectionSnapshot(
                        tool_key='tool-a',
                        document={'id': 'snapshot-a'},
                    ),
                ),
            )

    class _Publisher:
        def publish(self, tasks, *, assert_authority):
            assert_authority()
            assert len(tasks) == 1
            return (
                CosmosDispatchResult(
                    tool_key='tool-a',
                    published_documents=1,
                    error_type=None,
                ),
            )

    class _Context:
        def __init__(self):
            self.memory = {
                'ada_command_center.alarms.delivery.recovered': job,
            }
            self.facts = {}
            self.work = False

        def assert_lease_current(self):
            return None

        def get_memory(self, key):
            return self.memory.get(key)

        def set_iteration_fact(self, key, value):
            self.facts[key] = value

        def mark_iteration_work(self):
            self.work = True

    definition = JobDefinition(
        module_name='ada_command_center.processes.alarms_delivery',
        service_name='alarms-delivery',
        job_key='alarms-delivery',
        sleep_seconds=5,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
    job = AlarmDeliveryJob(
        definition=definition,
        receiver=_Receiver(),
        publisher=_Publisher(),
    )
    context = _Context()

    result = job.iteration(context)

    assert result.current_status == 'CURRENT_AVAILABLE'
    assert context.facts['alarm_delivery_published_documents'] == 1
    assert context.facts['alarm_delivery_failed_tools'] == 0
    assert context.work is True


def test_delivery_job_rejects_invalid_polling(tmp_path):
    with ParallelCosmosPublisher(
        connections={},
        max_workers=1,
        client_factory=lambda _: None,
    ) as publisher:
        with pytest.raises(ValueError, match='positive'):
            build_delivery_job(
                runtime_configuration=_configuration(tmp_path),
                source_key='alarm-configuration',
                publisher=publisher,
                poll_seconds=0,
            )
