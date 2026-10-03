# Espejo pedagógico en español del archivo productivo equivalente.
# Mantiene exactamente el mismo comportamiento; los comentarios explican la intención.
# Este incremento prioriza el flujo vertical Runtime -> Modeler -> Delivery -> Cosmos.

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ada_command_center.processes.alarms_modeler.receiver import (
    AlarmModelerCycleResult,
    LocalAlarmModeler,
)
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)

_MODULE = 'ada_command_center.processes.alarms_modeler'
_SERVICE = 'alarms-modeler'
_RECOVERY_KEY = 'ada_command_center.alarms.modeler.recovered'


@dataclass(slots=True)
class AlarmModelerJob:
    definition: JobDefinition
    modeler: LocalAlarmModeler

    def recover(self, context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        self.modeler.recover(context)
        context.set_memory(_RECOVERY_KEY, self)

    def iteration(self, context: JobRuntimeContext) -> AlarmModelerCycleResult:
        context.assert_lease_current()
        if context.get_memory(_RECOVERY_KEY) is not self:
            raise RuntimeError('Alarm Modeler recovery must precede iteration')
        result = self.modeler.model(context)
        context.set_iteration_fact('alarm_modeler_status', result.status)
        context.set_iteration_fact('alarm_modeler_projected_tools', result.projected_tools)
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


def build_alarm_modeler_job(
    *,
    runtime_configuration: RuntimeConfiguration,
    source_key: str,
    poll_seconds: float = 5.0,
) -> AlarmModelerJob:
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
    return AlarmModelerJob(
        definition=definition,
        modeler=LocalAlarmModeler(
            volume_path=runtime_configuration.volume_path,
            source_key=source_key,
        ),
    )
