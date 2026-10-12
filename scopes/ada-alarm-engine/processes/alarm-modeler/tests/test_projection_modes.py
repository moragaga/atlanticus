from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from ada.processes.alarm_modeler.projection import (
    AlarmModelerProjectionError,
    digest,
    has_semantic_change,
    project,
    validate_document,
)

from .test_projection import alarm, model, source


def process_projection(modes, *, now=None, slots=6, managed=()):
    configuration = model(*modes)
    for entry in configuration['alarms']:
        entry['visual_targets'][0]['process_projection_mode'] = modes[entry['identity']['alarm_key']]
    return project(
        current=source([alarm(name, managed=name in managed) for name in modes]),
        modeler_configuration=configuration,
        publication_tool_keys=('tool-a',),
        now=datetime.fromtimestamp(0, tz=UTC) if now is None else now,
        max_visible_slots=slots,
        rotation_seconds=30,
    )


def test_generic_process_preserves_normal_carousel():
    result = process_projection({'n1': 'GENERIC', 'n2': 'GENERIC'})
    tool = result['tools']['tool-a']
    assert result['schema_version'] == 3
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-n1'},
        {'slot': 2, 'occurrence_id': 'occ-n2'},
    ]
    assert tool['meta']['rotation_pending'] is False
    assert validate_document(result) == result


def test_one_distributed_uses_normal_carousel_order():
    tool = process_projection({'d1': 'DISTRIBUTED', 'n1': 'GENERIC'})['tools']['tool-a']
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-d1'},
        {'slot': 2, 'occurrence_id': 'occ-n1'},
    ]
    assert tool['meta']['operator_count'] == 2


def test_multiple_distributed_reserve_rightmost_slot_without_internal_selection():
    result = process_projection({
        'n1': 'GENERIC', 'd1': 'DISTRIBUTED', 'n2': 'GENERIC',
        'd2': 'DISTRIBUTED', 'd3': 'DISTRIBUTED',
    })
    tool = result['tools']['tool-a']
    assert set(tool['operator_pool']) == {'occ-n1', 'occ-n2', 'occ-d1', 'occ-d2', 'occ-d3'}
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-n1'},
        {'slot': 2, 'occurrence_id': 'occ-n2'},
        {'slot': 6, 'group': {
            'kind': 'DISTRIBUTED',
            'occurrence_ids': ['occ-d1', 'occ-d2', 'occ-d3'],
        }},
    ]
    assert tool['meta']['operator_count'] == 3
    assert tool['meta']['rotation_pending'] is False
    assert validate_document(result) == result


def test_group_without_normals_does_not_require_rotation():
    tool = process_projection({'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED'})['tools']['tool-a']
    assert tool['operator_view'] == [
        {'slot': 6, 'group': {
            'kind': 'DISTRIBUTED', 'occurrence_ids': ['occ-d1', 'occ-d2'],
        }},
    ]
    assert tool['meta']['rotation_pending'] is False


def test_group_rotates_only_normals_when_more_than_five():
    modes = {f'n{i}': 'GENERIC' for i in range(6)}
    modes.update({'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED'})
    first = process_projection(modes)
    second = process_projection(modes, now=datetime.fromtimestamp(30, tz=UTC))
    first_view = first['tools']['tool-a']['operator_view']
    second_view = second['tools']['tool-a']['operator_view']
    assert first_view[:5] != second_view[:5]
    assert first_view[-1] == second_view[-1]
    assert first['tools']['tool-a']['meta']['rotation_pending'] is True
    assert has_semantic_change(first, second)


def test_managed_distributed_alarm_is_not_counted_for_grouping():
    tool = process_projection(
        {'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED', 'n1': 'GENERIC'},
        managed=('d2',),
    )['tools']['tool-a']
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-d1'},
        {'slot': 2, 'occurrence_id': 'occ-n1'},
    ]
    assert tool['alarms']['occ-d2']['attention_required'] is False
    assert tool['meta']['rotation_pending'] is False


def test_unknown_process_mode_rejected():
    with pytest.raises(AlarmModelerProjectionError, match='projection mode'):
        process_projection({'d1': 'UNRECOGNIZED'})


def test_invalid_distributed_group_membership_is_rejected():
    result = process_projection({'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED', 'n1': 'GENERIC'})
    corrupted = deepcopy(result)
    corrupted['tools']['tool-a']['operator_view'][-1]['group']['occurrence_ids'].append('occ-n1')
    corrupted['sha256'] = digest({k: v for k, v in corrupted.items() if k != 'sha256'})
    with pytest.raises(AlarmModelerProjectionError, match='non-distributed'):
        validate_document(corrupted)


def test_source_schema_is_v2_and_old_output_is_not_accepted():
    result = process_projection({'n1': 'GENERIC'})
    old = deepcopy(result)
    old['schema_version'] = 1
    old['sha256'] = digest({k: v for k, v in old.items() if k != 'sha256'})
    with pytest.raises(AlarmModelerProjectionError, match='contract version'):
        validate_document(old)


def test_grouping_requires_documented_six_slot_layout():
    with pytest.raises(AlarmModelerProjectionError, match='six visible slots'):
        process_projection({'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED'}, slots=1)


def test_partial_distributed_group_is_rejected():
    result = process_projection({'d1': 'DISTRIBUTED', 'd2': 'DISTRIBUTED'})
    corrupted = deepcopy(result)
    corrupted['tools']['tool-a']['operator_view'][-1]['group']['occurrence_ids'] = ['occ-d1']
    corrupted['sha256'] = digest({k: v for k, v in corrupted.items() if k != 'sha256'})
    with pytest.raises(AlarmModelerProjectionError, match='distributed group'):
        validate_document(corrupted)
