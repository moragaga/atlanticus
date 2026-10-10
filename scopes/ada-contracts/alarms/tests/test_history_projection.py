from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from ada.contracts.alarms.history_projection import (
    AlarmHistoryDomain,
    AlarmHistoryProjectionError,
    project_committed_alarm_facts,
)


def _facts(records, *, segment='20261010T120000Z-0000', offset=127):
    return SimpleNamespace(
        commit={'commit_id': 'C-01', 'priority_group': 'plant'},
        journal_position={'segment_id': segment, 'byte_offset': offset, 'commit_id': 'C-01'},
        position=SimpleNamespace(record_sha256='a' * 64),
        records=records,
    )


def _project(records, *, stream='plant-primary'):
    return project_committed_alarm_facts(facts=_facts(records), stream_id=stream)


def test_lifecycle_uses_event_day_for_start_and_close() -> None:
    result = _project(
        {'occurrence_changes': [
            {'kind': 'STARTED', 'started_at': '2026-10-09T23:59:00Z',
             'occurrence_id': 'O-1', 'alarm_key': 'fam/rule'},
            {'kind': 'CLOSED', 'started_at': '2026-10-09T23:59:00Z',
             'ended_at': '2026-10-10T00:02:00Z', 'occurrence_id': 'O-1',
             'alarm_key': 'fam/rule', 'closure_reason': 'condition_normalized'},
        ]}
    )
    assert [row.domain for row in result.facts] == [AlarmHistoryDomain.LIFECYCLE] * 2
    assert [str(row.day_utc) for row in result.facts] == ['2026-10-09', '2026-10-10']
    assert [row.event_kind for row in result.facts] == ['STARTED', 'CLOSED']
    assert result.facts[0].occurrence_id == result.facts[1].occurrence_id


def test_simultaneous_assignments_are_three_independent_facts() -> None:
    records = {'assignment_changes': [
        {'change_id': f'A-{tool}', 'kind': 'ASSIGNED', 'occurrence_id': 'O-1',
         'alarm_key': 'fam/rule', 'tool_key': tool, 'effective_at': '2026-10-10T08:00:00Z'}
        for tool in ('tool-a', 'tool-b', 'tool-c')
    ]}
    rows = _project(records).facts
    assert len(rows) == 3
    assert len({row.historian_fact_id for row in rows}) == 3
    assert {row.domain for row in rows} == {AlarmHistoryDomain.VISIBILITY}
    assert {row.day_utc.isoformat() for row in rows} == {'2026-10-10'}
    assert {row.occurrence_id for row in rows} == {'O-1'}


def test_scheduled_is_not_relabelled_as_assigned() -> None:
    result = _project({'assignment_changes': [
        {'kind': 'SCHEDULED', 'change_id': 'A-1', 'occurrence_id': 'O-1', 'alarm_key': 'fam/rule',
         'tool_key': 'b', 'effective_at': '2026-10-10T08:00:00Z',
         'due_at': '2026-10-10T08:20:00Z'}]})
    assert result.facts[0].event_kind == 'SCHEDULED'
    assert '"due_at":"2026-10-10T08:20:00Z"' in result.facts[0].payload_json


def test_causal_cascade_preserves_source_and_effect_without_duplication() -> None:
    event = {
        'event_id': 'J-1', 'event_key': 'cascade_suppression_started',
        'effective_at': '2026-10-10T08:00:00Z', 'alarm_key': 'fam/risk',
        'occurrence_id': 'O-risk', 'cascade_source_alarm_key': 'fam/impact',
        'cascade_source_occurrence_id': 'O-impact',
        'cascade_management_effect_id': 'E-1',
    }
    first = _project({'journey_events': [event]})
    retry = _project({'journey_events': [deepcopy(event)]})
    assert first == retry
    assert first.facts[0].domain is AlarmHistoryDomain.CASCADE
    assert '"cascade_source_alarm_key":"fam/impact"' in first.facts[0].payload_json
    assert _project({'evidence_records': [
        {'evidence_id': 'X', 'recorded_at': '2026-10-10T08:05:00Z',
         'alarm_key': 'fam/risk', 'occurrence_id': 'O-risk', 'status': 'ACTIVE'}]}).facts[0].domain is AlarmHistoryDomain.EVIDENCE


def test_management_and_deactivation_receipts_preserve_actor_and_original_time() -> None:
    result = _project({'input_receipts': [
        {'input_id': 'M-1', 'input_kind': 'MANAGEMENT', 'commit_id': 'C-01',
         'outcome': 'EFFECTIVE', 'actor_key': 'person-1', 'alarm_key': 'fam/impact',
         'event_at': '2026-10-09T23:30:00Z', 'applied_at': '2026-10-10T00:10:00Z'},
        {'input_id': 'D-1', 'input_kind': 'DEACTIVATION_DECISION',
         'outcome': 'REJECTED', 'decision_kind': 'REJECTED', 'request_id': 'R-1',
         'actor_key': 'approver-1', 'event_at': '2026-10-10T01:00:00Z',
         'applied_at': '2026-10-10T01:10:00Z'},
    ]})
    management, deactivation = result.facts
    assert management.domain is AlarmHistoryDomain.MANAGEMENT
    assert management.day_utc.isoformat() == '2026-10-09'
    assert '"actor_key":"person-1"' in management.payload_json
    assert deactivation.domain is AlarmHistoryDomain.DEACTIVATION
    assert '"request_id":"R-1"' in deactivation.payload_json
    assert all(row.timestamp_provenance == 'SOURCE_EVENT_AT' for row in result.facts)


def test_old_receipt_is_explicit_about_limited_timestamp_provenance() -> None:
    result = _project({'input_receipts': [
        {'input_id': 'M-old', 'input_kind': 'MANAGEMENT',
         'outcome': 'EFFECTIVE', 'applied_at': '2026-10-10T01:10:00Z'}]})
    assert result.facts[0].timestamp_provenance == 'RECEIPT_APPLIED_AT'
    assert result.facts[0].alarm_key is None


def test_domain_sources_are_classified_and_exclusions_reported() -> None:
    result = _project({
        'management_effects': [{'kind': 'STARTED', 'record_id': 'ME-1', 'alarm_key': 'fam/rule',
                                'effective_at': '2026-10-10T09:00:00Z'}],
        'deactivation_requests': [{'requested_at': '2026-10-10T09:00:00Z',
                                   'alarm_key': 'fam/rule', 'request_id': 'DR-1',
                                   'source_occurrence_id': 'O-1'}],
        'deactivation_effects': [{'kind': 'CLEARED', 'record_id': 'DE-1', 'alarm_key': 'fam/rule',
                                  'effective_at': '2026-10-10T09:00:00Z'}],
        'journey_events': [
            {'event_id': 'J-2', 'event_key': 'management_applied', 'effective_at': '2026-10-10T09:00:00Z'},
            {'event_id': 'J-3', 'alarm_key': 'fam/rule', 'event_key': 'reappeared', 'effective_at': '2026-10-10T09:00:00Z'},
            {'event_id': 'J-4', 'event_key': 'technical_hold_started', 'effective_at': '2026-10-10T09:00:00Z'},
        ],
        'configuration_rebases': [{'schema_version': 'group-configuration-rebase.v1'}],
        'technical_incident_changes': [{'kind': 'STARTED'}],
    })
    assert {row.domain for row in result.facts} == {
        AlarmHistoryDomain.MANAGEMENT, AlarmHistoryDomain.DEACTIVATION
    }
    assert len(result.facts) == 4
    assert len(result.excluded) == 4
    assert {excluded.collection for excluded in result.excluded} == {
        'journey_events', 'configuration_rebases', 'technical_incident_changes'
    }


def test_fact_identity_is_stream_and_source_position_scoped() -> None:
    entries = {'evidence_records': [
        {'evidence_id': 'X-1', 'status': 'ACTIVE',
         'alarm_key': 'fam/rule', 'occurrence_id': 'O-1', 'recorded_at': '2026-10-10T01:00:00Z'}]}
    first = _project(entries)
    second = _project(entries, stream='another-runtime')
    assert first.facts[0].historian_fact_id != second.facts[0].historian_fact_id
    assert first.facts[0].historian_fact_id == _project(entries).facts[0].historian_fact_id


@pytest.mark.parametrize('records', [
    {'unsupported_events': [{'x': 1}]},
    {'journey_events': [{'event_key': 'new_unknown_event'}]},
    {'journey_events': [{'event_key': 'cascade_suppression_started',
                         'effective_at': '2026-10-10T01:00:00Z'}]},
    {'occurrence_changes': [{'kind': 'CLOSED', 'ended_at': None}]},
    {'evidence_records': [{'status': 'ACTIVE', 'alarm_key': 'fam/rule',
                           'occurrence_id': 'O-1', 'evidence_id': 'E-1', 'recorded_at': '2026-10-10T00:00:00+00:00'}]},
    {'input_receipts': [{'input_id': 'X-1', 'outcome': 'OTHER', 'input_kind': 'OTHER'}]},
])
def test_unknown_or_malformed_facts_fail_closed(records) -> None:
    with pytest.raises(AlarmHistoryProjectionError):
        _project(records)
