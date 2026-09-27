# Ciclo: adquirir candidato, obtener evidence, resolver B.2, revalidar y publicar.
# La publicación queda dentro de la sección fenced del Job Runtime.
# Un resultado previo del mismo candidato y evidence se comprueba y no se reescribe.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada_command_center.alarms.materialization import (
    AlarmResolutionStatus,
    resolve_alarm_configuration,
)
from ada_command_center.processes.alarms_materialization.acquisition import AlarmCandidateAcquirer
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublisher,
    result_id_for,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationError,
    AlarmQualificationProvider,
)
from atlanticus.runtime import JobRuntimeContext


# Contrato AlarmMaterializationOutcome: mantiene invariantes de esta frontera.
class AlarmMaterializationOutcome(StrEnum):
    READY = 'READY'
    BLOCKED = 'BLOCKED'
    UNCHANGED = 'UNCHANGED'


# Contrato AlarmMaterializationSupersededError: mantiene invariantes de esta frontera.
class AlarmMaterializationSupersededError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
# Contrato AlarmMaterializationIterationResult: mantiene invariantes de esta frontera.
class AlarmMaterializationIterationResult:
    outcome: AlarmMaterializationOutcome
    result_id: str


# Contrato AlarmMaterializationJob: mantiene invariantes de esta frontera.
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
        existing = self._publisher.get_existing(candidate, evidence)
        if existing is not None:
            if existing['status'] == 'READY':
                self._publisher.read_ready(
                    source_key=candidate.source_key.value, result_id=result_id
                )
            result = AlarmMaterializationIterationResult(
                outcome=AlarmMaterializationOutcome.UNCHANGED, result_id=result_id
            )
            self._record(context, candidate, result)
            return result
        context.raise_if_cancelled()
        projection = candidate.projection
        resolution = resolve_alarm_configuration(
            configuration=projection.payload.configuration,
            alarm_configuration_revision=candidate.alarm_configuration_revision,
            confirmed_tool_catalog=projection.payload.tool_dependencies,
            tool_qualification=evidence.tools,
            evaluator_qualification=evidence.evaluators,
        )
        context.raise_if_cancelled()
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

    @staticmethod
    def _record(context, candidate, result) -> None:
        context.set_iteration_fact('outcome', result.outcome.value)
        context.set_iteration_fact('result_id', result.result_id)
        context.set_iteration_fact('alarm_release', candidate.alarm_configuration_revision)
        context.set_iteration_fact('tool_revision', candidate.confirmed_tool_catalog_revision)
