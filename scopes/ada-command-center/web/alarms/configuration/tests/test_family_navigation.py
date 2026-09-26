from types import SimpleNamespace

import pytest

from ada_command_center.web.alarms.configuration.web import family_callbacks
from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.families import (
    add_message_in_family,
    add_rule_in_family,
    family_catalog,
    initial_navigation,
    require_new_family_key,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    ADD_RULE_BUTTON_ID,
    CREATE_FAMILY_ID,
    FAMILY_SELECT_TYPE,
    SHOW_GLOBAL_MESSAGES_ID,
)


class CallbackApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(function):
            self.callbacks[function.__name__] = function
            return function

        return register


def _callbacks():
    app = CallbackApp()
    family_callbacks.register_family_callbacks(app)
    return app.callbacks


def _trigger(monkeypatch, trigger, value=1):
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=trigger, triggered=[{'value': value}]),
    )


def test_families_derive_from_rules_and_messages_without_new_durable_aggregate() -> None:
    first = add_rule_in_family(empty_authoring_document(), 'mine')
    second = add_rule_in_family(first, 'plant')
    third = add_message_in_family(second, 'mine')
    fourth = add_message_in_family(third, None)
    before = {'rules': fourth['rules'].copy(), 'messages': fourth['messages'].copy()}

    grouped = family_catalog(fourth)

    assert [family.key for family in grouped.families] == ['mine', 'plant']
    assert grouped.get('mine').rule_indexes == (0,)
    assert grouped.get('mine').message_indexes == (0,)
    assert grouped.get('plant').rule_indexes == (1,)
    assert grouped.global_message_indexes == (1,)
    assert fourth == before
    assert set(fourth) == {'rules', 'messages'}


def test_message_only_family_exists_and_global_message_does_not_create_family() -> None:
    document = add_message_in_family(empty_authoring_document(), 'plant')
    document = add_message_in_family(document, None)

    catalog = family_catalog(document)

    assert len(catalog.families) == 1
    assert catalog.get('plant').message_indexes == (0,)
    assert catalog.global_message_indexes == (1,)
    assert document['messages'][1]['family_key'] is None
    assert document['messages'][1]['scope'] == 'GLOBAL'


def test_family_creation_requires_first_element_and_does_not_duplicate_existing_group():
    original = empty_authoring_document()
    assert family_catalog(original).families == ()
    assert require_new_family_key(original, 'mine') == 'mine'
    with pytest.raises(ValueError, match='empty'):
        require_new_family_key(original, ' ')
    with pytest.raises(ValueError, match='whitespace'):
        require_new_family_key(original, ' mine ')
    updated = add_rule_in_family(original, 'mine')
    assert family_catalog(updated).get('mine') is not None
    assert family_catalog(original).get('mine') is None
    with pytest.raises(ValueError, match='already exists'):
        require_new_family_key(updated, 'mine')


def test_new_rule_and_message_receive_family_before_becoming_valid() -> None:
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_message_in_family(document, 'mine')

    assert document['rules'][0]['identity']['family_key'] == 'mine'
    assert document['rules'][0]['identity']['alarm_key'].startswith('alarm-')
    assert document['messages'][0]['scope'] == 'FAMILY'
    assert document['messages'][0]['family_key'] == 'mine'


def test_navigation_uses_exact_document_indexes_not_filtered_display_indexes(monkeypatch):
    callbacks = _callbacks()
    document = add_rule_in_family(empty_authoring_document(), 'zeta')
    document = add_rule_in_family(document, 'alpha')
    _trigger(monkeypatch, {'type': FAMILY_SELECT_TYPE, 'index': 0})

    nav = callbacks['navigate'](None, None, [], [], [], [], initial_navigation(), document)

    assert nav['family_key'] == 'alpha'
    assert selected_family(nav, document) == 'alpha'
    _trigger(monkeypatch, ADD_RULE_BUTTON_ID)
    updated, selected = callbacks['add_family_item'](1, None, nav, document)
    assert updated['rules'][2]['identity']['family_key'] == 'alpha'
    assert selected['rule_index'] == 2
    assert document['rules'] != updated['rules']


def test_create_family_first_rule_or_message_updates_document_and_selection(monkeypatch):
    callbacks = _callbacks()
    original = empty_authoring_document()
    _trigger(monkeypatch, CREATE_FAMILY_ID)
    navigation, _result, cleared = callbacks['create_family'](
        1, 'mine', original, initial_navigation()
    )
    assert cleared == ''
    assert navigation['page'] == 'family'
    assert navigation['family_key'] == 'mine'
    assert family_catalog(original).families == ()
    _trigger(monkeypatch, ADD_RULE_BUTTON_ID)
    doc, selected = callbacks['add_family_item'](1, None, navigation, original)
    assert doc['rules'][0]['identity']['family_key'] == 'mine'
    assert selected['rule_index'] == 0
    assert selected['pending_families'] == []

    _trigger(monkeypatch, CREATE_FAMILY_ID)
    next_nav, _result, cleared = callbacks['create_family'](1, 'plant', doc, selected)
    assert cleared == ''
    assert next_nav['family_key'] == 'plant'
    assert family_catalog(doc).get('plant') is None


def test_global_navigation_keeps_rules_separate(monkeypatch):
    callbacks = _callbacks()
    document = add_message_in_family(empty_authoring_document(), None)
    _trigger(monkeypatch, SHOW_GLOBAL_MESSAGES_ID)

    nav = callbacks['navigate'](None, 1, [], [], [], [], initial_navigation(), document)
    assert nav['page'] == 'global'
    assert nav['tab'] == 'messages'
    assert selected_family(nav, document) is None
    assert callbacks['update_add_controls'](nav, document) == (True, False, True)


def test_detail_renders_only_selected_item_without_discarding_other_document_data() -> None:
    from ada_command_center.web.alarms.configuration.web.family_panel import build_active_editor

    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_rule_in_family(document, 'mine')
    document = add_message_in_family(document, 'mine')
    called_rules = []
    called_messages = []

    def rule_editor(index, *_args):
        called_rules.append(index)
        return 'rule editor'

    def message_editor(index, *_args):
        called_messages.append(index)
        return 'message editor'

    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mine',
        'tab': 'rules',
        'rule_index': 1,
    }
    build_active_editor(
        document, None, navigation, rule_editor=rule_editor, message_editor=message_editor
    )
    assert called_rules == [1]
    assert called_messages == []
    assert len(document['rules']) == 2
    assert len(document['messages']) == 1

    navigation['tab'] = 'messages'
    navigation['message_index'] = 0
    build_active_editor(
        document, None, navigation, rule_editor=rule_editor, message_editor=message_editor
    )
    assert called_rules == [1]
    assert called_messages == [0]
