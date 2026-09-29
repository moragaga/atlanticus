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
# El job conserva su propio lease y recuperación independientemente de Runtime.
class AlarmDeliveryInputJob:
    definition: JobDefinition
    receiver: LocalAlarmDeliveryReceiver

    # Rechaza composiciones que no pertenezcan al servicio Delivery.
    def __post_init__(self) -> None:
        if not isinstance(self.definition, JobDefinition):
            raise TypeError('definition must be a JobDefinition')
        if self.definition.module_name != _MODULE or self.definition.service_name != _SERVICE:
            raise ValueError('Job definition must identify the alarms-delivery service')
        if not isinstance(self.receiver, LocalAlarmDeliveryReceiver):
            raise TypeError('receiver must be LocalAlarmDeliveryReceiver')

    # La recuperación del receptor debe ocurrir antes de la primera iteración.
    def recover(self, context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        self.receiver.recover(context)
        context.set_memory(_RECOVERY_KEY, self)

    # La telemetría del ciclo contiene únicamente el estado de recepción CURRENT.
    def iteration(self, context: JobRuntimeContext) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        if context.get_memory(_RECOVERY_KEY) is not self:
            raise RuntimeError('Alarm Delivery input recovery must precede iteration')
        result = self.receiver.consume(context)
        context.set_iteration_fact('alarm_delivery_current_status', result.current_status)
        return result

    # El runtime común conserva ejecución, cancelación, fencing y lease.
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


# Construye el receptor CURRENT-only sin parámetros ni cursores para FACTS.
def build_delivery_input_job(
    *,
    runtime_configuration: RuntimeConfiguration,
    source_key: str,
    poll_seconds: float = 5.0,
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
        ),
    )
