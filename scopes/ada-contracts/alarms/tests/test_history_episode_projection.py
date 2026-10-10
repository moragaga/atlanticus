from __future__ import annotations

from types import SimpleNamespace

from ada.contracts.alarms.history_projection import (
    AlarmHistoryDomain,
    project_committed_alarm_facts,
)


def test_episode_changes_are_independent_from_occurrence_lifecycle():
    payload = {
        'episode_changes': [
            {'episode_id': 'EP-1', 'priority_group': 'group-A', 'kind': 'STARTED',
             'started_at': '2026-10-10T23:00:00Z', 'ended_at': None, 'closure_reason': None},
            {'episode_id': 'EP-1', 'priority_group': 'group-A', 'kind': 'CLOSED',
             'started_at': '2026-10-10T23:00:00Z', 'ended_at': '2026-10-11T02:00:00Z',
             'closure_reason': 'condition_normalized'},
        ],
        'occurrence_changes': [
            {'kind': 'STARTED', 'started_at': '2026-10-10T23:00:00Z',
             'episode_id': 'EP-1', 'occurrence_id': 'occ-1', 'alarm_key': 'family/rule-1'},
        ],
    }
    facts = SimpleNamespace(
        commit={'commit_id': 'C-1', 'priority_group': 'group-A'},
        journal_position={'segment_id': 'segment-1', 'byte_offset': 11, 'commit_id': 'C-1'},
        position=SimpleNamespace(record_sha256='a' * 64),
        records=payload,
    )
    result = project_committed_alarm_facts(facts=facts, stream_id='producer-A')
    episodes = [row for row in result.facts if row.domain is AlarmHistoryDomain.EPISODES]
    lifecycle = [row for row in result.facts if row.domain is AlarmHistoryDomain.LIFECYCLE]
    assert len(episodes) == 2
    assert [row.event_kind for row in episodes] == ['STARTED', 'CLOSED']
    assert [row.day_utc.isoformat() for row in episodes] == ['2026-10-10', '2026-10-11']
    assert len(lifecycle) == 1
    assert lifecycle[0].occurrence_id == 'occ-1'
    assert lifecycle[0].episode_id == 'EP-1'
    assert all(row.alarm_key is None for row in episodes)
