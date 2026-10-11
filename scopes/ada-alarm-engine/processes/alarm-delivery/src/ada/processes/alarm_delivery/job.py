from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ada.processes.alarm_delivery.checkpoint import AlarmDeliveryCheckpointStore
from ada.processes.alarm_delivery.contract import plan_tool_deliveries
from ada.processes.alarm_delivery.reader import ModelerCurrentReader
from ada.processes.alarm_delivery.transport import ParallelCosmosPublisher, destination_identity
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.runtime import JobRuntimeContext

_RECOVERY_KEY = 'ada.alarms.delivery.recovered'


class AlarmDeliveryPublicationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmDeliveryIterationResult:
    status: str
    published_tools: tuple[str, ...] = ()
    unchanged_tools: tuple[str, ...] = ()
    failed_tools: tuple[str, ...] = ()


@dataclass(slots=True)
class AlarmDeliveryJob:
    reader: ModelerCurrentReader
    checkpoint: AlarmDeliveryCheckpointStore
    publisher: ParallelCosmosPublisher
    connections: Mapping[str, CosmosSettings]

    def recover(self, context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        self.checkpoint.read()
        context.set_memory(_RECOVERY_KEY, self)

    def run_iteration(self, context: JobRuntimeContext) -> AlarmDeliveryIterationResult:
        context.assert_lease_current()
        if context.get_memory(_RECOVERY_KEY) is not self:
            raise RuntimeError('Alarm Delivery recovery must precede iteration')
        source = self.reader.read()
        if source is None:
            return AlarmDeliveryIterationResult(status='WAITING_MODELER')
        plan = plan_tool_deliveries(
            modeler_document=source,
            destination_identities={
                key: destination_identity(value) for key, value in self.connections.items()
            },
            confirmations=self.checkpoint.read(),
        )
        if not plan.pending:
            return AlarmDeliveryIterationResult(status='UNCHANGED', unchanged_tools=plan.unchanged)
        context.assert_lease_current()
        if self.reader.read() != source:
            return AlarmDeliveryIterationResult(status='SOURCE_CHANGED')
        results = self.publisher.publish(
            plan.pending, assert_authority=context.assert_lease_current
        )
        context.assert_lease_current()
        confirmed = []
        failures = []
        candidates = {item.tool_key: item for item in plan.pending}
        for result in results:
            if not result.successful:
                failures.append(result.tool_key)
                continue
            context.assert_lease_current()
            self.checkpoint.confirm(candidates[result.tool_key].confirmation())
            confirmed.append(result.tool_key)
        context.set_iteration_fact('alarm_delivery_published_tools', len(confirmed))
        context.set_iteration_fact('alarm_delivery_failed_tools', len(failures))
        if confirmed:
            context.mark_iteration_work()
        if failures:
            raise AlarmDeliveryPublicationError('One or more Tool destinations failed')
        return AlarmDeliveryIterationResult(
            status='PUBLISHED',
            published_tools=tuple(confirmed),
            unchanged_tools=plan.unchanged,
        )
