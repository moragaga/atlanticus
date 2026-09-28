from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ada_command_center.processes.alarms_runtime.composition import AlarmRuntimeComposition
from ada_command_center.processes.alarms_runtime.configured_iteration import _PINNED_MEMORY_KEY
from ada_command_center.processes.alarms_runtime.cycle import AlarmOperationalCycle
from ada_command_center.processes.alarms_runtime.inputs import AlarmOperationalInputs
from ada_command_center.processes.alarms_runtime.iteration import (
    AlarmIterationLoader,
    AlarmIterationSourceLoader,
)
from ada_command_center.processes.alarms_runtime.local_configuration import (
    RuntimeEffectiveConfiguration,
)
from ada_command_center.processes.alarms_runtime.publication import (
    AlarmCommittedFactsExporter,
    AlarmCurrentStatePublisher,
)
from ada_command_center.processes.alarms_runtime.session import AlarmExecutionSession
from atlanticus.operational_data.core import normalize_utc_second
from atlanticus.runtime import JobRuntimeContext

_RUNNER_MEMORY_KEY = 'ada_command_center.alarms.runtime.operational_runner.pinned'


def _now() -> datetime:
    return datetime.now(UTC)


def _empty_inputs(_context: JobRuntimeContext) -> AlarmOperationalInputs:
    return AlarmOperationalInputs()


@dataclass(frozen=True, slots=True)
class _BoundExecution:
    session: AlarmExecutionSession
    loader: AlarmIterationLoader
    cycle: AlarmOperationalCycle


@dataclass(slots=True)
class AlarmOperationalCycleRunner:
    composition: AlarmRuntimeComposition
    source_loader: AlarmIterationSourceLoader
    cycle_factory: Callable[[AlarmExecutionSession], AlarmOperationalCycle]
    clock: Callable[[], datetime] = field(default=_now)
    operational_inputs_provider: Callable[[JobRuntimeContext], AlarmOperationalInputs] = field(
        default=_empty_inputs
    )
    batch_exporter: AlarmCommittedFactsExporter | None = None
    current_publisher: AlarmCurrentStatePublisher | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.composition, AlarmRuntimeComposition):
            raise TypeError('composition must be AlarmRuntimeComposition')
        if not isinstance(self.source_loader, AlarmIterationSourceLoader):
            raise TypeError('source_loader must implement AlarmIterationSourceLoader')
        if not callable(self.cycle_factory):
            raise TypeError('cycle_factory must be callable')
        if not callable(self.clock):
            raise TypeError('clock must be callable')
        if not callable(self.operational_inputs_provider):
            raise TypeError('operational_inputs_provider must be callable')
        if self.batch_exporter is not None and not isinstance(
            self.batch_exporter, AlarmCommittedFactsExporter
        ):
            raise TypeError('batch_exporter must be AlarmCommittedFactsExporter or None')
        if self.current_publisher is not None and not isinstance(
            self.current_publisher, AlarmCurrentStatePublisher
        ):
            raise TypeError('current_publisher must be AlarmCurrentStatePublisher or None')

    def __call__(self, context: JobRuntimeContext, session: AlarmExecutionSession) -> bool:
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be JobRuntimeContext')
        if not isinstance(session, AlarmExecutionSession):
            raise TypeError('session must be AlarmExecutionSession')
        context.assert_lease_current()
        context.raise_if_cancelled()
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError('clock must return timezone-aware UTC datetime')
        as_of = normalize_utc_second(now.replace(microsecond=0), field_name='as_of')
        inputs = self.operational_inputs_provider(context)
        if not isinstance(inputs, AlarmOperationalInputs):
            raise TypeError('operational_inputs_provider must return AlarmOperationalInputs')
        blocked_until = self._blocked_until(session, inputs, as_of=as_of)
        if blocked_until is not None:
            context.set_next_iteration_delay(max(0.0, (blocked_until - now).total_seconds()))
            context.set_iteration_fact(
                'alarm_operational_cycle_status', 'waiting_for_distinct_group_second'
            )
            return False
        bound = context.get_or_create(_RUNNER_MEMORY_KEY, lambda: self._bind(session))
        if not isinstance(bound, _BoundExecution) or bound.session is not session:
            raise RuntimeError('operational runner session differs from the pinned job session')
        iteration = bound.loader.load(as_of=as_of)
        if self.batch_exporter is not None or self.current_publisher is not None:
            persistence = self.composition.durability.persistence
            pinned = context.get_memory(_PINNED_MEMORY_KEY)
            if (
                not isinstance(pinned, RuntimeEffectiveConfiguration)
                or pinned.revision.session is not session
            ):
                raise RuntimeError('Confirmed pinned EFFECTIVE session is required for publication')
            pin = pinned.effective_head.target_artifact_ref
            if (
                pin.alarm_configuration_revision != session.alarm_configuration_revision
                or pin.confirmed_tool_catalog_revision != session.tool_registry_revision
            ):
                raise RuntimeError('Current Engine session differs from confirmed EFFECTIVE')
            if self.batch_exporter is not None:
                self.batch_exporter.initialize_if_needed(
                    context=context, persistence=persistence, pin=pin
                )
        cycle_result = bound.cycle.execute(context, iteration, operational_inputs=inputs)
        if self.current_publisher is not None:
            self.current_publisher.publish(
                context=context, result=cycle_result, pin=pin, inputs=inputs
            )
        if self.batch_exporter is not None:
            self.batch_exporter.publish_unexported(
                context=context, persistence=persistence, pin=pin
            )
        context.set_iteration_fact('alarm_operational_cycle_status', 'executed')
        return True

    def _bind(self, session: AlarmExecutionSession) -> _BoundExecution:
        cycle = self.cycle_factory(session)
        if not isinstance(cycle, AlarmOperationalCycle):
            raise TypeError('cycle_factory must return AlarmOperationalCycle')
        if cycle.session is not session or cycle.composition is not self.composition:
            raise ValueError('cycle_factory must use the pinned session and shared composition')
        return _BoundExecution(
            session=session,
            loader=AlarmIterationLoader(session=session, source_loader=self.source_loader),
            cycle=cycle,
        )

    def _blocked_until(
        self,
        session: AlarmExecutionSession,
        inputs: AlarmOperationalInputs,
        *,
        as_of: datetime,
    ) -> datetime | None:
        persistence = self.composition.durability.persistence
        snapshots = persistence.list_snapshots()
        groups = {entry.planned_alarm.priority_group for entry in session.entries}
        groups.update(pending.priority_group for pending in inputs.pending_deactivation_requests)
        for snapshot in snapshots:
            document = snapshot.as_document()
            if document.get('episode') is not None or document['alarms']:
                groups.add(snapshot.priority_group)
        latest: datetime | None = None
        for snapshot in snapshots:
            if snapshot.priority_group not in groups:
                continue
            cycle_id, separator, group = snapshot.last_commit_id.partition('__')
            if not separator or group != snapshot.priority_group:
                raise RuntimeError('durable group last_commit_id is invalid')
            try:
                previous_at = datetime.strptime(cycle_id, '%Y%m%dT%H%M%S%fZ').replace(tzinfo=UTC)
            except ValueError as error:
                raise RuntimeError('durable group cycle_id is invalid') from error
            previous_second = previous_at.replace(microsecond=0)
            if previous_second >= as_of and (latest is None or previous_second > latest):
                latest = previous_second
        return None if latest is None else latest + timedelta(seconds=1)
