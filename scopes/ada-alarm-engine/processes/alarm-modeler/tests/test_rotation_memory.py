from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from ada.processes.alarm_modeler.rotation import (
    AlarmRotationError,
    ToolRotationMemory,
    plan_rotation,
)
from atlanticus.state import AtomicJsonStore


def _tool(key: str, keys: list[str], slots: int = 3) -> dict:
    return {
        'tool_key': key,
        'retired': False,
        'alarms': {item: {'occurrence_id': item} for item in keys},
        'operator_pool': list(keys),
        'operator_view': [],
        'meta': {
            'max_visible_slots': slots,
            'operator_count': 0,
            'rotation_pending': len(keys) > slots,
        },
    }


def _clock(second: int = 0) -> datetime:
    return datetime(2026, 10, 11, tzinfo=UTC) + timedelta(seconds=second)


def _visible(tool: dict) -> list[str]:
    return [entry['occurrence_id'] for entry in tool['operator_view']]


def test_stable_queue_serves_every_eligible_occurrence() -> None:
    tool = _tool('process-a', [f'alarm-{i}' for i in range(8)])
    state = None
    seen = set()
    previous = None
    for i in range(8):
        tool, state, due = plan_rotation(
            tool=tool, previous_tool=previous, state=state,
            now=_clock(i * 90), rotation_seconds=90,
        )
        seen.update(_visible(tool))
        previous = tool
        assert due == _clock((i + 1) * 90)
    assert seen == set(tool['operator_pool'])
    assert len(_visible(tool)) == 3


def test_new_arrivals_do_not_reset_existing_waiters() -> None:
    tool = _tool('process-a', ['a', 'b', 'c', 'd', 'e'])
    first, state, due = plan_rotation(
        tool=tool, previous_tool=None, state=None,
        now=_clock(), rotation_seconds=30,
    )
    assert _visible(first) == ['a', 'b', 'c']
    growing = _tool('process-a', ['x', 'a', 'b', 'c', 'd', 'e', 'f'])
    before, state, due = plan_rotation(
        tool=growing, previous_tool=first, state=state,
        now=_clock(10), rotation_seconds=30,
    )
    assert _visible(before) == ['a', 'b', 'c']
    assert due == _clock(30)
    after, state, due = plan_rotation(
        tool=growing, previous_tool=before, state=state,
        now=_clock(30), rotation_seconds=30,
    )
    assert _visible(after) == ['d', 'e', 'x']
    seen = set(_visible(after)) | set(_visible(first))
    for second in (60, 90, 120):
        after, state, due = plan_rotation(
            tool=growing, previous_tool=after, state=state,
            now=_clock(second), rotation_seconds=30,
        )
        seen.update(_visible(after))
    assert seen == set(growing['operator_pool'])


def test_tool_deadlines_are_independent() -> None:
    a = _tool('process-a', ['a1', 'a2', 'a3', 'a4'])
    b = _tool('process-b', ['b1', 'b2', 'b3', 'b4'])
    first_a, state_a, due_a = plan_rotation(
        tool=a, previous_tool=None, state=None, now=_clock(), rotation_seconds=90,
    )
    first_b, state_b, due_b = plan_rotation(
        tool=b, previous_tool=None, state=None, now=_clock(40), rotation_seconds=90,
    )
    assert due_a == _clock(90)
    assert due_b == _clock(130)
    a, state_a, _ = plan_rotation(
        tool=a, previous_tool=first_a, state=state_a, now=_clock(90), rotation_seconds=90,
    )
    b, state_b, _ = plan_rotation(
        tool=b, previous_tool=first_b, state=state_b, now=_clock(90), rotation_seconds=90,
    )
    assert _visible(a) != _visible(first_a)
    assert _visible(b) == _visible(first_b)


def test_preparation_not_published_does_not_advance_turn(tmp_path) -> None:
    memory = ToolRotationMemory(tmp_path)
    initial_tool = _tool('process-a', ['a', 'b', 'c', 'd'])
    first, current, _ = plan_rotation(
        tool=initial_tool, previous_tool=None, state=None,
        now=_clock(), rotation_seconds=30,
    )
    memory.prepare(
        tool_key='process-a', previous_tool=None, old_state=None,
        next_tool=first, next_state=current,
    )
    assert memory.read(tool_key='process-a', previous_tool=None) is None
    assert memory.read(tool_key='process-a', previous_tool=first) == current
    memory.confirm(tool_key='process-a', current_tool=first)
    second, next_state, _ = plan_rotation(
        tool=initial_tool, previous_tool=first, state=current,
        now=_clock(30), rotation_seconds=30,
    )
    memory.prepare(
        tool_key='process-a', previous_tool=first, old_state=current,
        next_tool=second, next_state=next_state,
    )
    assert memory.read(tool_key='process-a', previous_tool=first) == current
    assert memory.read(tool_key='process-a', previous_tool=second) == next_state
    memory.confirm(tool_key='process-a', current_tool=second)
    assert memory.read(tool_key='process-a', previous_tool=second) == next_state


def test_two_tools_persist_in_separate_files(tmp_path) -> None:
    memory = ToolRotationMemory(tmp_path)
    for key, alarms in [('process-a', ['a', 'b']), ('integrated-operations', ['x', 'y'])]:
        tool, state, _ = plan_rotation(
            tool=_tool(key, alarms), previous_tool=None, state=None,
            now=_clock(), rotation_seconds=90,
        )
        memory.prepare(
            tool_key=key, previous_tool=None, old_state=None,
            next_tool=tool, next_state=state,
        )
        memory.confirm(tool_key=key, current_tool=tool)
        assert memory.read(tool_key=key, previous_tool=tool) == state
    assert len(list((tmp_path / 'state' / 'rotation').glob('*.json'))) == 2


def test_corrupt_fingerprint_blocks_recovery(tmp_path) -> None:
    memory = ToolRotationMemory(tmp_path)
    tool, state, _ = plan_rotation(
        tool=_tool('process-a', ['a', 'b']), previous_tool=None, state=None,
        now=_clock(), rotation_seconds=90,
    )
    memory.prepare(
        tool_key='process-a', previous_tool=None, old_state=None,
        next_tool=tool, next_state=state,
    )
    memory.confirm(tool_key='process-a', current_tool=tool)
    changed = deepcopy(tool)
    changed['operator_pool'] = ['different']
    with pytest.raises(AlarmRotationError, match='disagrees'):
        memory.read(tool_key='process-a', previous_tool=changed)


def test_grouped_view_is_reserved_for_separate_policy() -> None:
    tool = _tool('integrated-operations', ['a', 'b'])
    tool['operator_view'] = [
        {'slot': 3, 'group': {'kind': 'DISTRIBUTED', 'occurrence_ids': ['a', 'b']}}
    ]
    with pytest.raises(AlarmRotationError, match='Distributed'):
        plan_rotation(
            tool=tool, previous_tool=None, state=None,
            now=_clock(), rotation_seconds=90,
        )
