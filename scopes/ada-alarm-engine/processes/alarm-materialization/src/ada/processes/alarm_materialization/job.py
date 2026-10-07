from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.alarms.materialization import (
    AlarmResolutionStatus,
    materialization_result_id,
    resolve_alarm_configuration,
)
from ada.alarms.persistence import LocalAlarmMaterializationStore
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationQualificationError,
    AlarmMaterializationSupersededError,
)
from ada.processes.alarm_materialization.qualification import AlarmQualificationProvider
from ada.processes.alarm_materialization.repository import AlarmConfigurationReader
from atlanticus.runtime import JobRuntimeContext

READINESS_RETRY_SECONDS = 30.0


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
        qualifications: AlarmQualificationProvider,
        store: LocalAlarmMaterializationStore,
    ) -> None:
        if not callable(getattr(reader, 'read_active', None)):
            raise TypeError('reader must provide read_active()')
        if not callable(getattr(qualifications, 'load', None)):
            raise TypeError('qualifications must provide load(candidate)')
        if not isinstance(store, LocalAlarmMaterializationStore):
            raise TypeError('store must be a LocalAlarmMaterializationStore')
        self._reader = reader
        self._qualifications = qualifications
        self._store = store

    def run_iteration(self, context: JobRuntimeContext) -> AlarmMaterializationIterationResult:
        context.raise_if_cancelled()
        try:
            candidate = self._reader.read_active()
        except AlarmMaterializationConfigurationPending:
            context.set_next_iteration_delay(READINESS_RETRY_SECONDS)
            result = AlarmMaterializationIterationResult(
                outcome=AlarmMaterializationOutcome.PENDING,
                result_id=None,
            )
            self._record(context, result=result, candidate=None)
            return result

        evidence = self._qualifications.load(candidate)
        evidence.validate_candidate(candidate)
        provenance = evidence.provenance(candidate)
        result_id = materialization_result_id(
            source_key=candidate.source_key,
            projection_digest=candidate.fingerprint,
            qualification_digest=evidence.digest,
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
            tool_qualification=evidence.tools,
            evaluator_qualification=evidence.evaluators,
        )

        context.raise_if_cancelled()
        self._revalidate(candidate, evidence.digest)
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

    def _revalidate(
        self, candidate: AlarmMaterializationCandidate, qualification_digest: str
    ) -> None:
        current = self._reader.read_active()
        if (
            current.source_release_id != candidate.source_release_id
            or current.fingerprint != candidate.fingerprint
        ):
            raise AlarmMaterializationSupersededError(
                'Alarm Configuration projection changed during materialization'
            )
        refreshed = self._qualifications.load(candidate)
        if refreshed.digest != qualification_digest:
            raise AlarmMaterializationQualificationError(
                'Alarm qualification evidence changed during materialization'
            )

    @staticmethod
    def _record(
        context: JobRuntimeContext,
        *,
        result: AlarmMaterializationIterationResult,
        candidate: AlarmMaterializationCandidate | None,
    ) -> None:
        context.set_iteration_fact('outcome', result.outcome.value)
        if result.result_id is not None:
            context.set_iteration_fact('result_id', result.result_id)
        if candidate is not None:
            context.set_iteration_fact('alarm_release', candidate.alarm_configuration_revision)
            context.set_iteration_fact('tool_revision', candidate.confirmed_tool_catalog_revision)
