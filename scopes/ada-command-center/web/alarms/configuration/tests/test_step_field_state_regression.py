from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from dash import no_update

from ada_command_center.web.alarms.configuration.web import callbacks, family_callbacks
from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.families import (
    add_rule_in_family,
    initial_navigation,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    PARAMETER_FIELD_TYPE,
    RULE_FIELD_TYPE,
    RULE_SECTION_TYPE,
    STEP_FIELD_TYPE,
)
from ada_command_center.web.alarms.configuration.web.parameters import (
    add_parameter,
    parameter_issues,
    parameter_rows,
    set_parameter_field,
)

from .test_workspace_hydration import _registered_callbacks, CallbackAppStub


def _field_event(identifier, value):
    return {
        'prop_id': json.dumps(identifier, sort_keys=True, separators=(',', ':')) + '.value',
        'value': value,
    }


def _update(monkeypatch, document, events):
    app, _ = _registered_callbacks()
    monkeypatch.setattr(
        callbacks,
        'ctx',
        SimpleNamespace(
            triggered=[_field_event(identifier, value) for identifier, value in events],
            triggered_id=events[0][0] if events else None,
        ),
    )
    return app.callbacks['update_authoring_fields'](
        [], [], [], [], [], [], document, None
    )


def _rule_field(field):
    return {'type': RULE_FIELD_TYPE, 'rule': 0, 'field': field}


def test_multiple_field_events_are_preserved_together(monkeypatch):
    original = add_rule_in_family(empty_authoring_document(), 'mine')
    updated = _update(
        monkeypatch,
        original,
        [
            (_rule_field('rule_name'), 'Temperature alert'),
            (_rule_field('display_name'), 'Temperature high'),
            (_rule_field('evaluator_key'), 'threshold'),
        ],
    )
    assert updated['rules'][0]['rule_name'] == 'Temperature alert'
    assert updated['rules'][0]['display_name'] == 'Temperature high'
    assert updated['rules'][0]['evaluator_key'] == 'threshold'
    assert original['rules'][0]['rule_name'] == ''


def test_invalid_field_does_not_discard_other_valid_events(monkeypatch):
    original = add_rule_in_family(empty_authoring_document(), 'mine')
    updated = _update(
        monkeypatch,
        original,
        [
            (_rule_field('unknown_field'), 'ignored'),
            (_rule_field('title'), 'Preserved title'),
        ],
    )
    assert updated['rules'][0]['title'] == 'Preserved title'


def test_non_field_mount_notifications_do_not_clear_authoring(monkeypatch):
    original = add_rule_in_family(empty_authoring_document(), 'mine')
    result = _update(
        monkeypatch,
        original,
        [({'type': 'unrelated-navigation'}, None)],
    )
    assert result is no_update
    assert original['rules'][0]['rule_name'] == ''


def test_edit_navigation_edit_preserves_unrelated_fields(monkeypatch):
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = _update(
        monkeypatch,
        document,
        [
            (_rule_field('rule_name'), 'Crushing temperature'),
            (_rule_field('cause_template'), 'Temperature above threshold'),
        ],
    )
    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mine',
        'rule_index': 0,
        'section': 'general',
    }
    app = CallbackAppStub()
    family_callbacks.register_family_callbacks(app)
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': RULE_SECTION_TYPE, 'section': 'evaluation'},
            triggered=[{'value': 1}],
        ),
    )
    after_nav = app.callbacks['select_rule_section']([], navigation, document)
    assert after_nav['section'] == 'evaluation'
    document = _update(monkeypatch, document, [(_rule_field('priority_group'), 'temperature')])
    assert document['rules'][0]['rule_name'] == 'Crushing temperature'
    assert document['rules'][0]['cause_template'] == 'Temperature above threshold'
    assert document['rules'][0]['priority_group'] == 'temperature'


def test_parameter_conversion_preserves_compatible_input_and_original():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_parameter(document, 0)
    document = set_parameter_field(document, 0, 0, 'key', 'threshold')
    document = set_parameter_field(document, 0, 0, 'value', '15,2')
    previous = deepcopy(document)
    converted = set_parameter_field(document, 0, 0, 'kind', 'FLOAT')
    assert converted['rules'][0]['parameters'] == {'threshold': 15.2}
    assert parameter_rows(converted['rules'][0])[0]['value'] == 15.2
    assert previous['rules'][0]['_parameter_rows'][0]['kind'] == 'TEXT'
    back = set_parameter_field(converted, 0, 0, 'kind', 'TEXT')
    assert back['rules'][0]['parameters'] == {'threshold': '15.2'}


def test_incompatible_parameter_value_is_reported_not_erased():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_parameter(document, 0)
    document = set_parameter_field(document, 0, 0, 'key', 'threshold')
    document = set_parameter_field(document, 0, 0, 'value', 'not-a-number')
    converted = set_parameter_field(document, 0, 0, 'kind', 'FLOAT')
    assert parameter_rows(converted['rules'][0])[0]['value'] == 'not-a-number'
    assert 'threshold' not in converted['rules'][0]['parameters']
    assert any('número' in issue for issue in parameter_issues(converted['rules'][0]))


def test_batch_parameter_edit_and_other_field(monkeypatch):
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_parameter(document, 0)
    updated = _update(
        monkeypatch,
        document,
        [
            ({'type': PARAMETER_FIELD_TYPE, 'rule': 0, 'parameter': 0, 'field': 'key'}, 'threshold'),
            (_rule_field('priority_order'), 1),
            ({'type': PARAMETER_FIELD_TYPE, 'rule': 0, 'parameter': 0, 'field': 'value'}, '90'),
        ],
    )
    assert updated['rules'][0]['parameters']['threshold'] == '90'
    assert updated['rules'][0]['priority_order'] == 1


def test_no_changes_return_no_update(monkeypatch):
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    app, _ = _registered_callbacks()
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered=[], triggered_id=None))
    assert app.callbacks['update_authoring_fields'](
        [], [], [], [], [], [], document, None
    ) is no_update
