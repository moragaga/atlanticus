from types import SimpleNamespace

import pytest
from dash import html, no_update

from ada_command_center.web.alarms.configuration.web import callbacks, family_callbacks
from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.families import (
    add_message_in_family,
    add_rule_in_family,
    family_catalog,
    initial_navigation,
    merged_family_catalog,
    remove_family,
)
from ada_command_center.web.alarms.configuration.web.family_panel import build_family_panel
from ada_command_center.web.alarms.configuration.web.ids import (
    FAMILY_REMOVE_TYPE,
    REMOVE_CONFIRM_ID,
)

from .test_admin_families import _callbacks
from .test_workspace_hydration import _registered_callbacks


def _elements(value):
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _elements(item)
    elif hasattr(value, 'children'):
        yield value
        yield from _elements(value.children)


def test_family_listing_has_independent_remove_actions():
    doc = add_rule_in_family(empty_authoring_document(), 'populated')
    nav = {**initial_navigation(), 'pending_families': ['unused']}
    listing = build_family_panel(
        doc, None, nav, rule_editor=lambda *args: None, message_editor=lambda *args: None
    )
    actions = [
        node.id['key']
        for node in _elements(listing)
        if isinstance(node, html.Button)
        and isinstance(node.id, dict)
        and node.id.get('type') == FAMILY_REMOVE_TYPE
    ]
    assert actions == ['populated', 'unused']


def test_remove_pending_family_is_navigation_only(monkeypatch):
    handlers = _callbacks()
    doc = empty_authoring_document()
    current = {**initial_navigation(), 'pending_families': ['unused', 'another']}
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': FAMILY_REMOVE_TYPE, 'key': 'unused'}, triggered=[{'value': 1}]
        ),
    )
    result = handlers['remove_pending_family']([], current, doc)
    assert result['pending_families'] == ['another']
    assert result['page'] == 'families'
    assert doc == empty_authoring_document()
    assert [entry.key for entry in merged_family_catalog(doc, result).families] == ['another']


def test_populated_family_requires_confirmation_and_only_removes_its_members(monkeypatch):
    app, _ = _registered_callbacks()
    doc = add_rule_in_family(empty_authoring_document(), 'populated')
    doc = add_message_in_family(doc, 'populated')
    doc = add_rule_in_family(doc, 'preserved')
    monkeypatch.setattr(
        callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': FAMILY_REMOVE_TYPE, 'key': 'populated'}, triggered=[{'value': 1}]
        ),
    )
    shown, message, pending, issue = app.callbacks['request_deletion']([], [], [1], doc)
    assert shown is True
    assert 'populated' in message
    assert issue is None
    assert pending['rule_indexes'] == [0]
    assert pending['message_indexes'] == [0]
    assert family_catalog(doc).get('populated') is not None
    monkeypatch.setattr(
        callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id=REMOVE_CONFIRM_ID,
            triggered=[{'prop_id': 'remove.submit_n_clicks', 'value': 1}],
        ),
    )
    result, navigation, cleared, feedback = app.callbacks['confirm_deletion'](
        1, None, pending, doc, initial_navigation()
    )
    assert [family.key for family in family_catalog(result).families] == ['preserved']
    assert navigation['page'] == 'families'
    assert cleared is None and feedback is None
    assert len(doc['rules']) == 2 and len(doc['messages']) == 1


def test_family_deletion_refuses_external_references_and_does_not_mutate_document():
    doc = add_rule_in_family(empty_authoring_document(), 'remove')
    doc = add_rule_in_family(doc, 'keep')
    identity = doc['rules'][0]['identity'].copy()
    doc['rules'][1]['reappearance']['special_conditions'] = [identity]
    with pytest.raises(ValueError, match='referenced by another family'):
        remove_family(doc, 'remove')
    assert len(doc['rules']) == 2


def test_cancelled_deletion_keeps_the_original_document(monkeypatch):
    app, _ = _registered_callbacks()
    doc = add_rule_in_family(empty_authoring_document(), 'keep')
    monkeypatch.setattr(
        callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id=REMOVE_CONFIRM_ID,
            triggered=[{'prop_id': 'remove.cancel_n_clicks', 'value': 1}],
        ),
    )
    result, navigation, pending, feedback = app.callbacks['confirm_deletion'](
        None, 1, {'kind': 'family', 'key': 'keep'}, doc, initial_navigation()
    )
    assert result is no_update and navigation is no_update
    assert pending is None and feedback is None
    assert len(doc['rules']) == 1
