from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from ada.processes.alarm_delivery.checkpoint import AlarmDeliveryCheckpointStore
from ada.processes.alarm_delivery.job import AlarmDeliveryJob
from ada.processes.alarm_delivery.reader import ModelerCurrentReader
from ada.processes.alarm_delivery.settings import AlarmDeliverySettings
from ada.processes.alarm_delivery.transport import ParallelCosmosPublisher
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.runtime.storage import resolve_application_root


@dataclass(slots=True)
class AlarmDeliveryComposition:
    configuration: ResolvedConfiguration
    settings: AlarmDeliverySettings
    job: AlarmDeliveryJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            recovery=self.job.recover,
            iteration=self.job.run_iteration,
            resource_scope=self._resource_scope,
            argv=argv,
            environ=self.configuration.values,
        )

    @contextmanager
    def _resource_scope(self, context: JobRuntimeContext) -> Iterator[None]:
        context.assert_lease_current()
        try:
            yield
        finally:
            self.job.publisher.close()


def build_composition(
    *,
    configuration: ResolvedConfiguration,
    connections: Mapping[str, CosmosSettings],
) -> AlarmDeliveryComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('Delivery configuration must be a ResolvedConfiguration')
    if (
        not isinstance(connections, Mapping)
        or not connections
        or any(
            not isinstance(key, str) or not isinstance(value, CosmosSettings)
            for key, value in connections.items()
        )
    ):
        raise ValueError('Delivery requires named Cosmos connections')
    settings = AlarmDeliverySettings.from_configuration(configuration)
    runtime = RuntimeConfiguration.from_sources(environ=configuration.values)
    source_root = resolve_application_root(
        runtime.volume_path, application=settings.modeler_application
    )
    publisher = ParallelCosmosPublisher(
        connections=connections,
        max_workers=settings.max_workers,
    )
    job = AlarmDeliveryJob(
        reader=ModelerCurrentReader(root=source_root / 'alarms' / 'modeler' / 'output'),
        checkpoint=AlarmDeliveryCheckpointStore(
            root=runtime.application_root / 'alarms' / 'delivery',
            modeler_application=settings.modeler_application,
        ),
        publisher=publisher,
        connections=dict(connections),
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_delivery',
        service_name='alarm-delivery',
        job_key='alarm-delivery',
        poll_interval_seconds=settings.poll_seconds,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
        iteration_summary_every=0,
    )
    return AlarmDeliveryComposition(configuration, settings, job, definition)
