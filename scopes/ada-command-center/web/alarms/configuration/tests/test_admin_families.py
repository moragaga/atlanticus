from types import SimpleNamespace

import pytest

from ada_command_center.web.alarms.configuration.web import family_callbacks
from ada_command_center.web.alarms.configuration.web.authoring import (
    empty_authoring_document,
    set_rule_field,
)
from ada_command_center.web.alarms.configuration.web.families import (
    add_rule_in_family,
    family_catalog,
    initial_navigation,
    merged_family_catalog,
    require_new_family_key,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    CLOSE_EDITOR_ID,
    CREATE_FAMILY_ID,
    SHOW_FAMILIES_ID,
)


class CallbackApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(func):
            self.callbacks[func.__name__] = func
            return func

        return register


def _callbacks():
    app = CallbackApp()
    family_callbacks.register_family_callbacks(app)
    return app.callbacks


def _trigger(monkeypatch, key):
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=key, triggered=[{'value': 1}]),
    )


def test_prepared_families_are_only_ephemeral_until_first_item():
    original = empty_authoring_document()
    nav = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mina',
        'pending_families': ['mina', 'planta'],
    }
    catalog = merged_family_catalog(original, nav)
    assert {family.key for family in catalog.families} == {'mina', 'planta'}
    assert family_catalog(original).families == ()
    assert selected_family(nav, original) == 'mina'
    updated = add_rule_in_family(original, 'mina')
    assert family_catalog(updated).get('mina') is not None
    assert family_catalog(updated).get('planta') is None
    assert set(updated) == {'rules', 'messages'}


def test_alarm_key_generated_at_creation_is_unique_and_stable():
    initial = empty_authoring_document()
    first = add_rule_in_family(initial, 'mina')
    key = first['rules'][0]['identity']['alarm_key']
    assert key.startswith('alarm-')
    assert key
    second = add_rule_in_family(first, 'mina')
    assert second['rules'][1]['identity']['alarm_key'] != key
    edited = set_rule_field(second, 0, 'display_name', 'Nombre diferente')
    assert edited['rules'][0]['identity']['alarm_key'] == key
    assert initial['rules'] == []


def test_prepared_families_cannot_be_duplicated():
    with pytest.raises(ValueError, match='already exists'):
        require_new_family_key(empty_authoring_document(), 'mina', pending=['mina'])


def test_pending_families_remain_available_during_navigation(monkeypatch):
    callbacks = _callbacks()
    doc = empty_authoring_document()
    _trigger(monkeypatch, CREATE_FAMILY_ID)
    nav, result, cleared = callbacks['create_family'](1, 'mina', doc, initial_navigation())
    assert nav['pending_families'] == ['mina']
    assert result is not None
    assert cleared == ''
    _trigger(monkeypatch, SHOW_FAMILIES_ID)
    updated = callbacks['navigate'](1, None, [], [], [], [], nav, doc)
    assert updated['pending_families'] == ['mina']
    assert updated['page'] == 'families'
    assert family_catalog(doc).families == ()


def test_close_editor_only_changes_navigation(monkeypatch):
    callbacks = _callbacks()
    doc = add_rule_in_family(empty_authoring_document(), 'mina')
    nav = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mina',
        'rule_index': 0,
        'section': 'visual',
    }
    _trigger(monkeypatch, CLOSE_EDITOR_ID)
    closed = callbacks['close_editor'](1, nav)
    assert closed['page'] == 'family'
    assert closed['family_key'] == 'mina'
    assert closed['rule_index'] is None
    assert closed['message_index'] is None
    assert doc['rules'][0]['identity']['family_key'] == 'mina'


def test_identity_cannot_be_changed_through_authoring_fields():
    document = add_rule_in_family(empty_authoring_document(), 'mina')
    key = document['rules'][0]['identity']['alarm_key']
    for field in ('identity.family_key', 'identity.alarm_key'):
        with pytest.raises(ValueError, match='cannot be edited'):
            set_rule_field(document, 0, field, 'other')
    assert document['rules'][0]['identity'] == {'family_key': 'mina', 'alarm_key': key}


def test_family_creation_is_available_only_on_family_list():
    callbacks = _callbacks()
    assert callbacks['show_family_creation'](initial_navigation()) is False
    assert callbacks['show_family_creation']({**initial_navigation(), 'page': 'family'}) is True
    assert callbacks['show_family_creation']({**initial_navigation(), 'page': 'global'}) is True
