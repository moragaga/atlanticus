from __future__ import annotations

from ada.contracts.alarms import AlarmConfigurationSnapshot
from ada_command_center.processes.alarms_materialization.candidate import (
    AlarmMaterializationCandidate,
)
from ada_command_center.processes.alarms_materialization.errors import (
    AlarmCandidateContractError,
    AlarmCandidateMismatchError,
    AlarmCandidateUnavailableError,
)
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseRef


class AlarmCandidateAcquirer:
    def __init__(
        self,
        *,
        projection: ProjectionStore[AlarmConfigurationSnapshot],
        source_key: SourceKey,
    ) -> None:
        if not isinstance(source_key, SourceKey):
            raise TypeError('source_key must be a SourceKey')
        self._projection = projection
        self._source_key = source_key

    def acquire(
        self,
        *,
        expected_release: SourceReleaseRef | None = None,
    ) -> AlarmMaterializationCandidate:
        if expected_release is not None and not isinstance(expected_release, SourceReleaseRef):
            raise TypeError('expected_release must be a SourceReleaseRef')
        record = self._projection.get_active(self._source_key)
        if record is None:
            raise AlarmCandidateUnavailableError('Alarm Configuration projection is unavailable')
        if record.source_key != self._source_key:
            raise AlarmCandidateMismatchError('Alarm Configuration projection source key mismatch')
        if expected_release is not None and record.source_release != expected_release:
            raise AlarmCandidateMismatchError('Alarm Configuration projection release mismatch')
        try:
            candidate = AlarmMaterializationCandidate.capture(record)
            candidate_projection = candidate.projection
        except (AlarmConfigurationProjectionError, TypeError, ValueError) as error:
            raise AlarmCandidateContractError(
                'Alarm Configuration projection contract is invalid'
            ) from error
        if candidate_projection.source_key != self._source_key:
            raise AlarmCandidateMismatchError('Alarm Configuration projection source key mismatch')
        if expected_release is not None and candidate_projection.source_release != expected_release:
            raise AlarmCandidateMismatchError('Alarm Configuration projection release mismatch')
        return candidate
