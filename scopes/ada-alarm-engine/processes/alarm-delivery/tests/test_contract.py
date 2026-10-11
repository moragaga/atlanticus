import json
from copy import deepcopy
from hashlib import sha256

import pytest

from ada.processes.alarm_delivery import (
    AlarmDeliveryContractError,
    ToolDeliveryConfirmation,
    plan_tool_deliveries,
)


def _digest(document):
    return sha256(
        json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False
        ).encode('utf-8')
    ).hexdigest()


def _tool(key, *, alarms=None, view=None, retired=False):
    return {
        'tool_key': key,
        'retired': retired,
        'alarms': {} if alarms is None else alarms,
        'operator_pool': [],
        'operator_view': [] if view is None else view,
        'meta': {
            'live_count': 0 if alarms is None else len(alarms),
            'attention_count': 0,
            'operator_count': 0 if view is None else len(view),
            'max_visible_slots': 6,
            'rotation_pending': False,
        },
    }


def _source(*, tools=None, at='2026-10-11T12:00:00Z', position=1, revision='r1'):
    document = {
        'document_type': 'ada_alarm_modeler_live_projection',
        'schema_version': 2,
        'artifact_ref': {
            'source_key': 'alarm-configuration',
            'result_id': 'alarm-materialization-' + 'a' * 64,
            'manifest_sha256': 'b' * 64,
            'resolution_key': {
                'alarm_configuration_revision': revision,
                'confirmed_tool_catalog_revision': 't1',
            },
        },
        'source_journal_position': {
            'segment_id': '2026-10-11T12Z#0000',
            'byte_offset': position,
            'commit_id': f'c{position}',
        },
        'source_as_of': at,
        'tools': {'tool_a': _tool('tool_a'), 'tool_b': _tool('tool_b')} if tools is None else tools,
    }
    document['sha256'] = _digest(document)
    return document


def _seal(source):
    source['sha256'] = _digest({key: value for key, value in source.items() if key != 'sha256'})
    return source


def _destinations():
    return {'tool_a': 'cosmos-a/db/live', 'tool_b': 'cosmos-b/db/live'}


def _confirmed(plan):
    return {candidate.tool_key: candidate.confirmation() for candidate in plan.pending}


def test_first_plan_dispatches_each_tool_to_its_own_destination():
    plan = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    assert [candidate.tool_key for candidate in plan.pending] == ['tool_a', 'tool_b']
    assert [candidate.destination_identity for candidate in plan.pending] == [
        'cosmos-a/db/live',
        'cosmos-b/db/live',
    ]
    assert plan.unchanged == ()


def test_confirmed_candidates_do_not_repeat_on_polling_or_restart():
    source = _source()
    first = plan_tool_deliveries(
        modeler_document=source, destination_identities=_destinations(), confirmations={}
    )
    receipts = {
        key: ToolDeliveryConfirmation.from_document(value.to_document())
        for key, value in _confirmed(first).items()
    }
    for _ in range(3):
        plan = plan_tool_deliveries(
            modeler_document=deepcopy(source),
            destination_identities=_destinations(),
            confirmations=receipts,
        )
        assert plan.pending == ()
        assert plan.unchanged == ('tool_a', 'tool_b')


def test_change_in_one_tool_dispatches_only_that_tool():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source(position=2)
    source['tools']['tool_b']['alarms']['o1'] = {'status': 'ACTIVE'}
    source['tools']['tool_b']['meta']['live_count'] = 1
    _seal(source)
    plan = plan_tool_deliveries(
        modeler_document=source,
        destination_identities=_destinations(),
        confirmations=_confirmed(first),
    )
    assert [candidate.tool_key for candidate in plan.pending] == ['tool_b']
    assert plan.unchanged == ('tool_a',)


def test_source_timestamp_and_position_only_do_not_trigger_delivery():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source(position=2, at='2026-10-11T12:00:01Z')
    plan = plan_tool_deliveries(
        modeler_document=source,
        destination_identities=_destinations(),
        confirmations=_confirmed(first),
    )
    assert plan.pending == ()


def test_rotation_changes_only_the_affected_tool():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source()
    source['tools']['tool_b']['operator_view'] = [{'slot': 1, 'occurrence_id': 'o1'}]
    source['tools']['tool_b']['meta']['operator_count'] = 1
    _seal(source)
    plan = plan_tool_deliveries(
        modeler_document=source,
        destination_identities=_destinations(),
        confirmations=_confirmed(first),
    )
    assert [candidate.tool_key for candidate in plan.pending] == ['tool_b']


def test_configuration_revision_change_republishes_provenance():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    second = plan_tool_deliveries(
        modeler_document=_source(position=2, revision='r2'),
        destination_identities=_destinations(),
        confirmations=_confirmed(first),
    )
    assert [candidate.tool_key for candidate in second.pending] == ['tool_a', 'tool_b']


def test_retired_tool_is_a_real_empty_snapshot():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source(position=2)
    source['tools']['tool_a'] = _tool('tool_a', retired=True)
    _seal(source)
    second = plan_tool_deliveries(
        modeler_document=source,
        destination_identities=_destinations(),
        confirmations=_confirmed(first),
    )
    assert [candidate.tool_key for candidate in second.pending] == ['tool_a']
    assert second.pending[0].tool['retired'] is True
    assert second.pending[0].tool['alarms'] == {}


def test_missing_retirement_snapshot_is_rejected():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source(tools={'tool_a': _tool('tool_a')})
    with pytest.raises(AlarmDeliveryContractError, match='retirement snapshot'):
        plan_tool_deliveries(
            modeler_document=source,
            destination_identities=_destinations(),
            confirmations=_confirmed(first),
        )


def test_destination_change_triggers_publication():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    destinations = {**_destinations(), 'tool_a': 'cosmos-a/db2/live'}
    second = plan_tool_deliveries(
        modeler_document=_source(),
        destination_identities=destinations,
        confirmations=_confirmed(first),
    )
    assert [candidate.tool_key for candidate in second.pending] == ['tool_a']


def test_missing_destination_rejects_full_batch():
    with pytest.raises(AlarmDeliveryContractError, match='no delivery destination'):
        plan_tool_deliveries(
            modeler_document=_source(),
            destination_identities={'tool_a': 'cosmos-a/db/live'},
            confirmations={},
        )


def test_invalid_source_digest_is_rejected_before_dispatch():
    source = _source()
    source['tools']['tool_a']['operator_view'].append({'slot': 1})
    with pytest.raises(AlarmDeliveryContractError, match='checksum mismatch'):
        plan_tool_deliveries(
            modeler_document=source,
            destination_identities=_destinations(),
            confirmations={},
        )


def test_unsupported_schema_is_rejected():
    source = _source()
    source['schema_version'] = 1
    _seal(source)
    with pytest.raises(AlarmDeliveryContractError, match='unsupported'):
        plan_tool_deliveries(
            modeler_document=source,
            destination_identities=_destinations(),
            confirmations={},
        )


def test_corrupt_confirmation_is_rejected():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    document = first.pending[0].confirmation().to_document()
    document['semantic_sha256'] = 'INVALID'
    with pytest.raises(AlarmDeliveryContractError, match='SHA-256'):
        ToolDeliveryConfirmation.from_document(document)


def test_older_source_than_confirmed_delivery_is_rejected():
    first = plan_tool_deliveries(
        modeler_document=_source(position=2),
        destination_identities=_destinations(),
        confirmations={},
    )
    with pytest.raises(AlarmDeliveryContractError, match='precedes'):
        plan_tool_deliveries(
            modeler_document=_source(position=1),
            destination_identities=_destinations(),
            confirmations=_confirmed(first),
        )


def test_same_journal_position_with_different_commit_id_is_rejected():
    first = plan_tool_deliveries(
        modeler_document=_source(), destination_identities=_destinations(), confirmations={}
    )
    source = _source()
    source['source_journal_position']['commit_id'] = 'changed'
    _seal(source)
    with pytest.raises(AlarmDeliveryContractError, match='precedes'):
        plan_tool_deliveries(
            modeler_document=source,
            destination_identities=_destinations(),
            confirmations=_confirmed(first),
        )


def test_candidate_and_confirmation_do_not_alias_source_document():
    source = _source()
    candidate = plan_tool_deliveries(
        modeler_document=source, destination_identities=_destinations(), confirmations={}
    ).pending[0]
    confirmation = candidate.confirmation()
    source['tools']['tool_a']['meta']['live_count'] = 500
    source['source_journal_position']['byte_offset'] = 100
    assert candidate.tool['meta']['live_count'] == 0
    assert confirmation.source_journal_position['byte_offset'] == 1
