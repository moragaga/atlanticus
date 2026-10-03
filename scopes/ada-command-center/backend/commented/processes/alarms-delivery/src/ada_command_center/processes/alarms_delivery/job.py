# Espejo pedagógico del job productivo.
# Una iteración sólo se marca como trabajo cuando Delivery publicó al menos un documento.
# Esto hace que las métricas work/empty del runtime representen correctamente la publicación.

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ada_command_center.processes.alarms_delivery.parallel import (
    CosmosDispatchTask,
    ParallelCosmosPublisher,
)
from ada_command_center.processes.alarms_delivery.receiver import (
    DeliveryInputCycleResult,
    LocalAlarmDeliveryReceiver,
)
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)

_MODULE = 'ada_command_center.processes.alarms_delivery'
_SERVICE = 'alarms-delivery'
_RECOVERY_KEY = 'ada_command_center.alarms.delivery.recovered'


class AlarmDeliveryPublicationError(RuntimeError):
    pass


@dataclass(slots=True)
class AlarmDeliveryJob:
    definition: JobDefinition
    receiver: LocalAlarmDeliveryReceiver
    publisher: ParallelCosmosPublisher

    def recover(self, context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        self.receiver.recover(context)
        context.set_memory(_RECOVERY_KEY, self)

    def iteration(self, context: JobRuntimeContext) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        if context.get_memory(_RECOVERY_KEY) is not self:
            raise RuntimeError('Alarm Delivery recovery must precede iteration')
        result = self.receiver.consume(context)
        context.set_iteration_fact('alarm_delivery_current_status', result.current_status)
        if result.current_status != 'CURRENT_AVAILABLE':
            return result
        published = self.publisher.publish(
            tuple(
                CosmosDispatchTask(
                    tool_key=snapshot.tool_key,
                    documents=(snapshot.document,),
                )
                for snapshot in result.snapshots
            ),
            assert_authority=context.assert_lease_current,
        )
        failures = tuple(item for item in published if not item.successful)
        published_documents = sum(item.published_documents for item in published)
        context.set_iteration_fact(
            'alarm_delivery_published_documents',
            published_documents,
        )
        context.set_iteration_fact('alarm_delivery_failed_tools', len(failures))
        if failures:
            raise AlarmDeliveryPublicationError(
                'One or more alarm projection destinations failed'
            )
        if published_documents > 0:
            context.mark_iteration_work()
        return result

    def execute(
        self,
        *,
        argv: Sequence[str] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            recovery=self.recover,
            iteration=self.iteration,
            argv=argv,
            environ=environ,
        )


def build_delivery_job(
    *,
    runtime_configuration: RuntimeConfiguration,
    source_key: str,
    publisher: ParallelCosmosPublisher,
    poll_seconds: float = 5.0,
) -> AlarmDeliveryJob:
    if not isinstance(runtime_configuration, RuntimeConfiguration):
        raise TypeError('runtime_configuration must be RuntimeConfiguration')
    if not isinstance(publisher, ParallelCosmosPublisher):
        raise TypeError('publisher must be ParallelCosmosPublisher')
    if not isinstance(poll_seconds, int | float) or isinstance(poll_seconds, bool):
        raise ValueError('poll_seconds must be a positive number')
    if not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise ValueError('poll_seconds must be a positive finite number')
    definition = JobDefinition(
        module_name=_MODULE,
        service_name=_SERVICE,
        job_key=_SERVICE,
        sleep_seconds=float(poll_seconds),
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
    return AlarmDeliveryJob(
        definition=definition,
        receiver=LocalAlarmDeliveryReceiver(
            volume_path=runtime_configuration.volume_path,
            source_key=source_key,
        ),
        publisher=publisher,
    )
