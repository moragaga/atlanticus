from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
_RECOVERY_KEY = 'ada_command_center.alarms.delivery.input.recovered'


@dataclass(slots=True)
# El job tiene lease y estado de recuperación propios, separados de Engine.
class AlarmDeliveryInputJob:
    definition: JobDefinition
    receiver: LocalAlarmDeliveryReceiver

    def __post_init__(self) -> None:
        if not isinstance(self.definition, JobDefinition):
            raise TypeError('definition must be a JobDefinition')
        if self.definition.module_name != _MODULE or self.definition.service_name != _SERVICE:
            raise ValueError('Job definition must identify the alarms-delivery service')
        if not isinstance(self.receiver, LocalAlarmDeliveryReceiver):
            raise TypeError('receiver must be LocalAlarmDeliveryReceiver')

    # Valida el inbox antes de permitir una iteración.
    def recover(self, context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        self.receiver.recover(context)
        context.set_memory(_RECOVERY_KEY, self)

    # La iteración sólo recibe entradas; Live Projection es un incremento posterior.
    def iteration(self, context: JobRuntimeContext) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        if context.get_memory(_RECOVERY_KEY) is not self:
            raise RuntimeError('Alarm Delivery input recovery must precede iteration')
        result = self.receiver.consume(context)
        context.set_iteration_fact('alarm_delivery_current_status', result.current_status)
        context.set_iteration_fact('alarm_delivery_received_facts', result.staged_facts)
        if result.last_facts_batch_id is not None:
            context.set_iteration_fact('alarm_delivery_last_facts_batch_id', result.last_facts_batch_id)
        return result

    # Delega ejecución, lease, fencing y señales al runtime compartido.
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


# Construye la composición explícita sin importar el ejecutable de Engine.
def build_delivery_input_job(
    *,
    runtime_configuration: RuntimeConfiguration,
    source_key: str,
    poll_seconds: float = 5.0,
    max_facts_per_iteration: int = 100,
) -> AlarmDeliveryInputJob:
    if not isinstance(runtime_configuration, RuntimeConfiguration):
        raise TypeError('runtime_configuration must be RuntimeConfiguration')
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
    return AlarmDeliveryInputJob(
        definition=definition,
        receiver=LocalAlarmDeliveryReceiver(
            volume_path=runtime_configuration.volume_path,
            source_key=source_key,
            max_facts_per_iteration=max_facts_per_iteration,
        ),
    )
