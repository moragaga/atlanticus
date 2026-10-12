from __future__ import annotations

from copy import deepcopy

from ada.processes.alarm_delivery import plan_tool_deliveries

from .test_contract import _confirmed, _destinations, _seal, _source, _tool


def test_cause_text_refresh_only_dispatches_affected_tool_with_same_cursor():
    first = _source(tools={
        'tool_a': _tool('tool_a', alarms={'occ-a': {'cause_text': 'Presión 125 bar'}}),
        'tool_b': _tool('tool_b', alarms={'occ-b': {'cause_text': 'Equipo operativo'}}),
    })
    initial_plan = plan_tool_deliveries(
        modeler_document=first, destination_identities=_destinations(), confirmations={}
    )
    changed = deepcopy(first)
    changed['tools']['tool_a']['alarms']['occ-a']['cause_text'] = 'Presión 132 bar'
    _seal(changed)
    updated = plan_tool_deliveries(
        modeler_document=changed,
        destination_identities=_destinations(),
        confirmations=_confirmed(initial_plan),
    )
    assert first['source_journal_position'] == changed['source_journal_position']
    assert [candidate.tool_key for candidate in updated.pending] == ['tool_a']
    assert updated.unchanged == ('tool_b',)
    confirmed = _confirmed(initial_plan)
    confirmed.update(_confirmed(updated))
    repeated = plan_tool_deliveries(
        modeler_document=changed, destination_identities=_destinations(),
        confirmations=confirmed,
    )
    assert repeated.pending == ()
