from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from ada.alarms.materialization import modeler_to_document
from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
)
from ada.contracts.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada.processes.alarm_modeler.projection import (
    AlarmModelerProjectionError,
    digest,
    has_semantic_change,
    project,
    validate_document,
)
from ada.processes.alarm_modeler.distributed_rotation import plan_distributed_rotation
from ada.processes.alarm_modeler.presentation_policy import (
    QUEUE_IN_QUEUE_ROTATION_SECONDS,
    QUEUE_IN_QUEUE_SLOTS_PER_AREA,
)
from ada.processes.alarm_modeler.rotation import ToolRotationMemory, is_grouped, plan_rotation
from atlanticus.state import AtomicJsonStore

_CURRENT = 'current/latest.json'
_EFFECTIVE = 'runtime/state/effective-head.json'


@dataclass(frozen=True, slots=True)
class AlarmModelerCycleResult:
    status: str
    live_alarms: int = 0
    attention_alarms: int = 0
    tools: int = 0


@dataclass(slots=True)
class AlarmModelerProcessor:
    runtime_root: Path
    output_root: Path
    rotation_seconds: float
    max_visible_slots: int
    queue_rotation_seconds: float = QUEUE_IN_QUEUE_ROTATION_SECONDS
    queue_slots_per_area: int = QUEUE_IN_QUEUE_SLOTS_PER_AREA
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _last_source_digest: str | None = field(default=None, init=False, repr=False)
    _last_output_digest: str | None = field(default=None, init=False, repr=False)
    _next_rotation_at: datetime | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.runtime_root.is_absolute() or not self.output_root.is_absolute():
            raise ValueError('Modeler roots must be absolute paths')
        if not callable(self.clock):
            raise TypeError('Modeler clock must be callable')

    def recover(self, context: object) -> None:
        context.assert_lease_current()
        previous = AtomicJsonStore(root_path=self.output_root, max_document_bytes=None).read(
            _CURRENT
        )
        if previous is not None:
            validate_document(previous)

    def run_iteration(self, context: object) -> AlarmModelerCycleResult:
        context.assert_lease_current()
        runtime_store = AtomicJsonStore(
            root_path=self.runtime_root / 'alarms', max_document_bytes=None
        )
        effective_document = runtime_store.read(_EFFECTIVE)
        if effective_document is None:
            return AlarmModelerCycleResult(status='WAITING_EFFECTIVE')
        effective = AlarmEffectiveConfigurationHead.from_document(effective_document)
        reference = effective.target_artifact_ref
        if reference.source_key != ALARM_CONFIGURATION_SOURCE_KEY:
            raise AlarmModelerProjectionError('Runtime EFFECTIVE source key is invalid')
        current_store = AtomicJsonStore(
            root_path=self.runtime_root / 'alarms' / 'output', max_document_bytes=None
        )
        source = current_store.read(_CURRENT)
        if source is None:
            return AlarmModelerCycleResult(status='WAITING_CURRENT')
        source = validate_document(source, source=True)
        pin = AlarmArtifactRefSnapshot.from_document(source['artifact_ref'])
        if pin != reference:
            return AlarmModelerCycleResult(status='WAITING_CURRENT')
        output = AtomicJsonStore(root_path=self.output_root, max_document_bytes=None)
        previous = output.read(_CURRENT)
        if previous is not None:
            previous = validate_document(previous)
        now = self.clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() != UTC.utcoffset(now)
        ):
            raise AlarmModelerProjectionError('Modeler clock must be UTC')
        if (
            previous is not None
            and self._last_source_digest == source['sha256']
            and self._last_output_digest == previous['sha256']
            and (self._next_rotation_at is None or now < self._next_rotation_at)
        ):
            return AlarmModelerCycleResult(status='SKIPPED')
        ready = LocalAlarmMaterializationStore(
            root=materialization_root(self.runtime_root)
        ).read_ready(
            source_key=pin.source_key,
            result_id=pin.result_id,
            expected_manifest_sha256=pin.manifest_sha256,
        )
        if (
            ready.engine.resolution_key != ready.modeler.resolution_key
            or ready.modeler.resolution_key != ready.delivery.resolution_key
        ):
            raise AlarmModelerProjectionError('Materialization revisions differ')
        document = project(
            current=source,
            modeler_configuration=modeler_to_document(ready.modeler),
            publication_tool_keys=ready.delivery.publication_tool_keys,
            previous=previous,
            now=now,
            rotation_seconds=self.rotation_seconds,
            max_visible_slots=self.max_visible_slots,
        )
        memory = ToolRotationMemory(self.output_root)
        prepared = {}
        due_times = []
        for tool_key, tool in document['tools'].items():
            old_tool = None if previous is None else previous['tools'].get(tool_key)
            old_state = memory.read(tool_key=tool_key, previous_tool=old_tool)
            if is_grouped(tool):
                planned_tool, planned_state, due_at = plan_distributed_rotation(
                    tool=tool, previous_tool=old_tool, state=old_state, now=now,
                    carousel_seconds=self.rotation_seconds,
                    queue_seconds=self.queue_rotation_seconds,
                    slots_per_area=self.queue_slots_per_area,
                )
            else:
                rotation_state = (
                    None if isinstance(old_state, dict) and 'normal' in old_state
                    else old_state
                )
                if rotation_state is None and old_tool is not None and not is_grouped(old_tool):
                    _, rotation_state, _ = plan_rotation(
                        tool=old_tool, previous_tool=old_tool, state=None,
                        now=now, rotation_seconds=self.rotation_seconds,
                    )
                planned_tool, planned_state, due_at = plan_rotation(
                    tool=tool, previous_tool=old_tool, state=rotation_state,
                    now=now, rotation_seconds=self.rotation_seconds,
                )
            document['tools'][tool_key] = planned_tool
            prepared[tool_key] = (old_tool, old_state, planned_tool, planned_state)
            if due_at is not None:
                due_times.append(due_at)
        document['sha256'] = digest({key: value for key, value in document.items() if key != 'sha256'})
        changed = has_semantic_change(previous, document)
        context.assert_lease_current()
        with context.fenced_mutation():
            if (
                runtime_store.read(_EFFECTIVE) != effective_document
                or current_store.read(_CURRENT) != source
            ):
                return AlarmModelerCycleResult(status='SOURCE_CHANGED')
            existing = output.read(_CURRENT)
            if existing is not None:
                existing = validate_document(existing)
            if existing != previous:
                return AlarmModelerCycleResult(status='OUTPUT_CHANGED')
            for tool_key, (old_tool, old_state, planned_tool, planned_state) in prepared.items():
                memory.prepare(
                    tool_key=tool_key, previous_tool=old_tool, old_state=old_state,
                    next_tool=planned_tool, next_state=planned_state,
                )
            if changed:
                output.replace(_CURRENT, document)
            for tool_key, (_, _, planned_tool, _) in prepared.items():
                memory.confirm(tool_key=tool_key, current_tool=planned_tool)
        self._remember(source, document if changed else previous, due_times)
        if not changed:
            return AlarmModelerCycleResult(status='SKIPPED')
        return AlarmModelerCycleResult(
            status='PUBLISHED',
            live_alarms=sum(len(tool['alarms']) for tool in document['tools'].values()),
            attention_alarms=sum(len(tool['operator_pool']) for tool in document['tools'].values()),
            tools=len(document['tools']),
        )

    def _remember(self, source: dict, document: dict, due_times: list[datetime]) -> None:
        self._last_source_digest = source['sha256']
        self._last_output_digest = document['sha256']
        self._next_rotation_at = min(due_times) if due_times else None
