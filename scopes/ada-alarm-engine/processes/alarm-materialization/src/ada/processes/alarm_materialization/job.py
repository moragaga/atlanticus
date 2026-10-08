from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ada.alarms.materialization import (
    AlarmMaterializationProvenance,
    AlarmResolutionStatus,
    materialization_result_id,
    resolve_alarm_configuration,
)
from ada.alarms.persistence import LocalAlarmMaterializationStore
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationSupersededError,
)
from ada.processes.alarm_materialization.repository import AlarmConfigurationReader
from atlanticus.runtime import JobRuntimeContext

READINESS_RETRY_SECONDS = 30.0
READINESS_MAX_ATTEMPTS = 3


class AlarmMaterializationOutcome(StrEnum):
    READY = 'READY'
    BLOCKED = 'BLOCKED'
    UNCHANGED = 'UNCHANGED'
    PENDING = 'PENDING'


@dataclass(frozen=True, slots=True)
class AlarmMaterializationIterationResult:
    outcome: AlarmMaterializationOutcome
    result_id: str | None


class AlarmMaterializationJob:
    def __init__(
        self,
        *,
        reader: AlarmConfigurationReader,
        store: LocalAlarmMaterializationStore,
        readiness_retry_seconds: float = READINESS_RETRY_SECONDS,
    ) -> None:
        if not callable(getattr(reader, 'read_active', None)):
            raise TypeError('reader must provide read_active()')
        if not isinstance(store, LocalAlarmMaterializationStore):
            raise TypeError('store must be a LocalAlarmMaterializationStore')
        if (
            isinstance(readiness_retry_seconds, bool)
            or not isinstance(readiness_retry_seconds, int | float)
            or not math.isfinite(readiness_retry_seconds)
            or readiness_retry_seconds <= 0
        ):
            raise ValueError('readiness_retry_seconds must be a positive finite number')
        self._reader = reader
        self._store = store
        self._readiness_retry_seconds = float(readiness_retry_seconds)

    def run_iteration(self, context: JobRuntimeContext) -> AlarmMaterializationIterationResult:
        candidate = self._acquire(context)
        if candidate is None:
            result = AlarmMaterializationIterationResult(
                outcome=AlarmMaterializationOutcome.PENDING,
                result_id=None,
            )
            self._record(context, result=result, candidate=None)
            return result

        provenance = AlarmMaterializationProvenance(
            source_release_id=candidate.source_release_id,
            source_published_at_utc=candidate.projection.source_published_at_utc.isoformat(),
            confirmed_tool_catalog_revision=candidate.confirmed_tool_catalog_revision,
            projection_digest=candidate.fingerprint,
        )
        result_id = materialization_result_id(
            source_key=candidate.source_key,
            projection_digest=candidate.fingerprint,
        )
        existing = self._store.read_result(
            source_key=candidate.source_key,
            result_id=result_id,
        )

        context.raise_if_cancelled()
        projection = candidate.projection
        resolution = resolve_alarm_configuration(
            configuration=projection.snapshot.configuration,
            alarm_configuration_revision=candidate.alarm_configuration_revision,
            confirmed_tool_catalog=projection.snapshot.tool_dependencies,
        )

        context.raise_if_cancelled()
        self._revalidate(candidate)
        context.assert_lease_current()
        with context.fenced_mutation():
            publication = self._store.publish(
                source_key=candidate.source_key,
                provenance=provenance,
                resolution=resolution,
            )

        changed = existing is None or publication.promoted_ready
        if changed:
            context.mark_iteration_work()
        if not changed:
            outcome = AlarmMaterializationOutcome.UNCHANGED
        elif resolution.status is AlarmResolutionStatus.READY:
            outcome = AlarmMaterializationOutcome.READY
        else:
            outcome = AlarmMaterializationOutcome.BLOCKED
        result = AlarmMaterializationIterationResult(
            outcome=outcome,
            result_id=publication.result_id,
        )
        self._record(context, result=result, candidate=candidate)
        return result

    def _acquire(self, context: JobRuntimeContext) -> AlarmMaterializationCandidate | None:
        for attempt in range(READINESS_MAX_ATTEMPTS):
            context.raise_if_cancelled()
            try:
                return self._reader.read_active()
            except AlarmMaterializationConfigurationPending:
                if attempt == READINESS_MAX_ATTEMPTS - 1:
                    return None
                if not context.wait(self._readiness_retry_seconds):
                    context.raise_if_cancelled()
                    return None
        return None

    def _revalidate(self, candidate: AlarmMaterializationCandidate) -> None:
        current = self._reader.read_active()
        if (
            current.source_release_id != candidate.source_release_id
            or current.fingerprint != candidate.fingerprint
        ):
            raise AlarmMaterializationSupersededError(
                'Alarm Configuration projection changed during materialization'
            )

    @staticmethod
    def _record(
        context: JobRuntimeContext,
        *,
        result: AlarmMaterializationIterationResult,
        candidate: AlarmMaterializationCandidate | None,
    ) -> None:
        context.set_iteration_fact('outcome', result.outcome.value)
        context.set_execution_fact('materialization_outcome', result.outcome.value)
        if result.result_id is not None:
            context.set_iteration_fact('result_id', result.result_id)
        if candidate is not None:
            context.set_iteration_fact('alarm_release', candidate.alarm_configuration_revision)
            context.set_iteration_fact('tool_revision', candidate.confirmed_tool_catalog_revision)
