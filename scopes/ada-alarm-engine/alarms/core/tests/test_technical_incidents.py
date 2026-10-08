from dataclasses import replace
from datetime import timedelta

import pytest

from ada.alarms.core import (
    AffectedInputIssue,
    AlarmStatus,
    EvaluationError,
    TechnicalIncident,
    TechnicalIncidentChangeKind,
    TechnicalIncidentResolution,
    reduce_initial_technical_incidents,
    technical_error_fingerprint,
)

from .support import NOW, error, identity, physical


def _reduce(previous=(), evaluations=(), *, at=NOW, groups=None, occurrences=frozenset()):
    mapping = {identity('risk'): 'mill-feed'} if groups is None else groups
    return reduce_initial_technical_incidents(
        previous,
        evaluations=evaluations,
        executable_groups=mapping,
        physical_occurrences=occurrences,
        cycle_at=at,
    )


def test_1200_identical_errors_create_exactly_one_start() -> None:
    state = ()
    changes = []
    for i in range(1200):
        at = NOW + timedelta(seconds=3 * i)
        result = _reduce(state, (error('risk', at=at),), at=at)
        state = result.open_incidents
        changes.extend(result.changes)
    assert len(changes) == 1
    assert changes[0].kind is TechnicalIncidentChangeKind.STARTED
    assert len(state) == 1
    assert state[0].started_at == NOW
    assert state[0].changed_at == NOW


def test_changed_error_creates_one_transition_and_return_to_a_is_new_change() -> None:
    first = _reduce(evaluations=(error('risk'),))
    at = NOW + timedelta(seconds=3)
    changed = _reduce(first.open_incidents, (error('risk', at=at, error_key='other'),), at=at)
    assert len(changed.changes) == 1
    assert changed.changes[0].kind is TechnicalIncidentChangeKind.CHANGED
    assert changed.open_incidents[0].incident_id == first.open_incidents[0].incident_id
    repeated = _reduce(
        changed.open_incidents,
        (error('risk', at=at + timedelta(seconds=3), error_key='other'),),
        at=at + timedelta(seconds=3),
    )
    assert repeated.changes == ()
    at += timedelta(seconds=6)
    back = _reduce(repeated.open_incidents, (error('risk', at=at),), at=at)
    assert len(back.changes) == 1
    assert back.changes[0].kind is TechnicalIncidentChangeKind.CHANGED
    assert back.open_incidents[0].fingerprint == first.open_incidents[0].fingerprint
    assert back.changes[0].record_id != changed.changes[0].record_id


def test_valid_evaluation_resolves_once_and_next_failure_starts_new_incident() -> None:
    first = _reduce(evaluations=(error('risk'),))
    at = NOW + timedelta(seconds=3)
    resolved = _reduce(
        first.open_incidents,
        (physical('risk', AlarmStatus.INACTIVE, at=at),),
        at=at,
    )
    assert resolved.open_incidents == ()
    assert len(resolved.changes) == 1
    assert resolved.changes[0].kind is TechnicalIncidentChangeKind.RESOLVED
    assert resolved.changes[0].resolution is TechnicalIncidentResolution.VALID_EVALUATION
    next_at = at + timedelta(seconds=3)
    next_valid = _reduce((), (physical('risk', AlarmStatus.INACTIVE, at=next_at),), at=next_at)
    assert next_valid.changes == ()
    at += timedelta(seconds=6)
    next_error = _reduce((), (error('risk', at=at),), at=at)
    assert next_error.changes[0].kind is TechnicalIncidentChangeKind.STARTED
    assert next_error.open_incidents[0].incident_id != first.open_incidents[0].incident_id


def test_restore_open_incident_without_restarting_or_duplicating() -> None:
    first = _reduce(evaluations=(error('risk'),))
    stored = first.open_incidents[0].as_document()
    restored = TechnicalIncident.from_document(stored)
    assert restored == first.open_incidents[0]
    at = NOW + timedelta(seconds=3)
    continued = _reduce((restored,), (error('risk', at=at),), at=at)
    assert continued.open_incidents == (restored,)
    assert continued.changes == ()
    corrupted = dict(stored)
    corrupted['fingerprint'] = 'sha256:' + '0' * 64
    with pytest.raises(ValueError, match='fingerprint'):
        TechnicalIncident.from_document(corrupted)


def test_same_error_on_two_alarms_creates_two_independent_incidents() -> None:
    groups = {identity('risk'): 'mill-feed', identity('impact'): 'mill-feed'}
    first = _reduce(
        evaluations=(error('risk'), error('impact')),
        groups=groups,
    )
    assert len(first.open_incidents) == 2
    assert len(first.changes) == 2
    assert len({item.incident_id for item in first.open_incidents}) == 2
    assert len({item.fingerprint for item in first.open_incidents}) == 2
    at = NOW + timedelta(seconds=3)
    second = _reduce(
        first.open_incidents,
        (error('risk', at=at), physical('impact', AlarmStatus.ACTIVE, at=at)),
        at=at,
        groups=groups,
    )
    assert len(second.open_incidents) == 1
    assert second.open_incidents[0].alarm_identity == identity('risk')
    assert len(second.changes) == 1
    assert second.changes[0].kind is TechnicalIncidentChangeKind.RESOLVED


def test_message_and_affected_input_order_do_not_fabricate_new_incident() -> None:
    original = error('risk')
    a = AffectedInputIssue(reason_key='missing', source_key='PI', fields=('B', 'A'))
    b = AffectedInputIssue(reason_key='timeout', source_key='SQL')
    original = replace(
        original,
        error=EvaluationError(
            origin=original.error.origin,
            error_key=original.error.error_key,
            message='Message 1',
            affected_inputs=(a, b),
        ),
    )
    first = _reduce(evaluations=(original,))
    at = NOW + timedelta(seconds=3)
    repeated = replace(
        original,
        evaluated_at=at,
        error=replace(
            original.error,
            message='Message 2, varying timestamp 42',
            affected_inputs=(b, replace(a, fields=('A', 'B'))),
        ),
    )
    assert technical_error_fingerprint(
        original.alarm_identity, original.error
    ) == technical_error_fingerprint(repeated.alarm_identity, repeated.error)
    result = _reduce(first.open_incidents, (repeated,), at=at)
    assert result.changes == ()
    assert result.open_incidents == first.open_incidents


def test_initial_error_does_not_open_incident_when_physical_occurrence_exists() -> None:
    value = _reduce(
        evaluations=(error('risk'),),
        occurrences=frozenset({identity('risk')}),
    )
    assert value.open_incidents == ()
    assert value.changes == ()


def test_configuration_withdrawn_resolves_without_fabricating_valid_evaluation() -> None:
    first = _reduce(evaluations=(error('risk'),))
    at = NOW + timedelta(seconds=3)
    withdrawn = _reduce(first.open_incidents, at=at, groups={})
    assert withdrawn.open_incidents == ()
    assert len(withdrawn.changes) == 1
    assert withdrawn.changes[0].resolution is TechnicalIncidentResolution.CONFIGURATION_WITHDRAWN


def test_duplicate_evaluation_and_invalid_timestamp_fail_closed() -> None:
    with pytest.raises(ValueError, match='unique'):
        _reduce(evaluations=(error('risk'), error('risk')))
    with pytest.raises(ValueError, match='match cycle_at'):
        _reduce(evaluations=(error('risk', at=NOW + timedelta(seconds=3)),))
