from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada_command_center.alarms.materialization import (
    AlarmResolutionStatus,
    resolve_alarm_configuration,
)
from ada_command_center.processes.alarms_materialization.acquisition import AlarmCandidateAcquirer
from ada_command_center.processes.alarms_materialization.candidate import (
    AlarmMaterializationCandidate,
)
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublisher,
    result_id_for,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationError,
    AlarmQualificationEvidence,
    AlarmQualificationProvider,
)
from atlanticus.runtime import JobRuntimeContext


class AlarmMaterializationOutcome(StrEnum):
    READY = 'READY'
    BLOCKED = 'BLOCKED'
    UNCHANGED = 'UNCHANGED'


class AlarmMaterializationSupersededError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmMaterializationIterationResult:
    outcome: AlarmMaterializationOutcome
    result_id: str


# Orquestación de I/O; el resolver permanece puro y no conoce rutas ni almacenamiento.
class AlarmMaterializationJob:
    def __init__(
        self,
        *,
        acquirer: AlarmCandidateAcquirer,
        qualifications: AlarmQualificationProvider,
        publisher: AlarmMaterializationPublisher,
    ) -> None:
        self._acquirer = acquirer
        self._qualifications = qualifications
        self._publisher = publisher

    def run_iteration(self, context: JobRuntimeContext) -> AlarmMaterializationIterationResult:
        context.raise_if_cancelled()
        candidate = self._acquirer.acquire()
        evidence = self._qualifications.load(candidate)
        evidence.validate_candidate(candidate)
        result_id = result_id_for(candidate, evidence)
        # Reconocemos la misma identidad incluso si el intento previo terminó antes de promover READY.
        existing = self._publisher.get_existing(candidate, evidence)
        if existing is not None:
            if existing['status'] == 'READY':
                self._publisher.read_ready(
                    source_key=candidate.source_key.value, result_id=result_id
                )
                # Solo la versión completa puede promocionarse; antes revalidamos proyección y qualification.
                if not self._publisher.is_current_ready(candidate, evidence):
                    context.raise_if_cancelled()
                    self._revalidate(candidate, evidence)
                    context.assert_lease_current()
                    with context.fenced_mutation():
                        promoted = self._publisher.promote_ready(candidate, evidence)
                    if promoted:
                        context.mark_iteration_work()
                    result = AlarmMaterializationIterationResult(
                        outcome=(
                            AlarmMaterializationOutcome.READY
                            if promoted
                            else AlarmMaterializationOutcome.UNCHANGED
                        ),
                        result_id=result_id,
                    )
                    self._record(context, candidate, result)
                    return result
            result = AlarmMaterializationIterationResult(
                outcome=AlarmMaterializationOutcome.UNCHANGED, result_id=result_id
            )
            self._record(context, candidate, result)
            return result
        context.raise_if_cancelled()
        projection = candidate.projection
        # B.2 recibe exactamente la revisión y el manifiesto Tool congelados en el candidato.
        resolution = resolve_alarm_configuration(
            configuration=projection.payload.configuration,
            alarm_configuration_revision=candidate.alarm_configuration_revision,
            confirmed_tool_catalog=projection.payload.tool_dependencies,
            tool_qualification=evidence.tools,
            evaluator_qualification=evidence.evaluators,
        )
        context.raise_if_cancelled()
        self._revalidate(candidate, evidence)
        context.assert_lease_current()
        with context.fenced_mutation():
            result_id = self._publisher.publish(candidate, evidence, resolution)
        context.mark_iteration_work()
        result = AlarmMaterializationIterationResult(
            outcome=(
                AlarmMaterializationOutcome.READY
                if resolution.status is AlarmResolutionStatus.READY
                else AlarmMaterializationOutcome.BLOCKED
            ),
            result_id=result_id,
        )
        self._record(context, candidate, result)
        return result

    # El input debe seguir siendo el mismo inmediatamente antes de escribir o cambiar READY.
    def _revalidate(
        self, candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
    ) -> None:
        current = self._acquirer.acquire(expected_release=candidate.source_release)
        if current.fingerprint != candidate.fingerprint:
            raise AlarmMaterializationSupersededError(
                'Alarm Configuration projection changed during materialization'
            )
        refreshed = self._qualifications.load(candidate)
        if refreshed.digest != evidence.digest:
            raise AlarmQualificationError(
                'Alarm qualification evidence changed during materialization'
            )

    @staticmethod
    def _record(context, candidate, result) -> None:
        context.set_iteration_fact('outcome', result.outcome.value)
        context.set_iteration_fact('result_id', result.result_id)
        context.set_iteration_fact('alarm_release', candidate.alarm_configuration_revision)
        context.set_iteration_fact('tool_revision', candidate.confirmed_tool_catalog_revision)
