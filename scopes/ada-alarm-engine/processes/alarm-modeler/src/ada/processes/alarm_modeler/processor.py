from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import floor
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
    has_semantic_change,
    project,
    validate_document,
)
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
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _last_source_digest: str | None = field(default=None, init=False, repr=False)
    _last_output_digest: str | None = field(default=None, init=False, repr=False)
    _last_rotation_phase: int | None = field(default=None, init=False, repr=False)
    _rotation_pending: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.runtime_root.is_absolute() or not self.output_root.is_absolute():
            raise ValueError('Modeler roots must be absolute paths')
        if not callable(self.clock):
            raise TypeError('Modeler clock must be callable')

    def recover(self, context: object) -> None:
        context.assert_lease_current()
        previous = AtomicJsonStore(root_path=self.output_root, max_document_bytes=None).read(_CURRENT)
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
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
            raise AlarmModelerProjectionError('Modeler clock must be UTC')
        rotation_phase = floor(now.timestamp() / self.rotation_seconds)
        if (
            previous is not None
            and self._last_source_digest == source['sha256']
            and self._last_output_digest == previous['sha256']
            and (not self._rotation_pending or self._last_rotation_phase == rotation_phase)
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
        if not has_semantic_change(previous, document):
            self._remember(source, document, rotation_phase)
            return AlarmModelerCycleResult(status='SKIPPED')
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
            output.replace(_CURRENT, document)
        self._remember(source, document, rotation_phase)
        return AlarmModelerCycleResult(
            status='PUBLISHED',
            live_alarms=sum(len(tool['alarms']) for tool in document['tools'].values()),
            attention_alarms=sum(len(tool['operator_pool']) for tool in document['tools'].values()),
            tools=len(document['tools']),
        )

    def _remember(self, source: dict, document: dict, phase: int) -> None:
        self._last_source_digest = source['sha256']
        self._last_output_digest = document['sha256']
        self._last_rotation_phase = phase
        self._rotation_pending = any(
            len(tool['operator_pool']) > self.max_visible_slots
            for tool in document['tools'].values()
        )
