from dataclasses import replace
from types import SimpleNamespace

import pytest
from dash import no_update

from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.web.alarms.configuration.web import callbacks
from ada_command_center.web.alarms.configuration.web.families import initial_navigation
from ada_command_center.web.alarms.configuration.web.ids import (
    MODAL_SAVE_BUTTON_ID,
    SAVE_BUTTON_ID,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.workspace import ManagerWorkspace

from .helpers import configuration
from .test_workspace_hydration import CallbackAppStub, _context, _registered_callbacks


def test_footer_save_persists_the_current_manager_workspace(monkeypatch):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    revision = callbacks._editor_revision(AlarmConfiguration.from_document(document), current)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=SAVE_BUTTON_ID))

    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        None, 1, None, document, current, revision, navigation
    )

    assert updated is not no_update
    assert updated == saved
    assert AlarmConfiguration.from_document(
        dict(ManagerWorkspace.from_document(updated).payload)
    ) == AlarmConfiguration.from_document(document)
    assert 'Borrador guardado' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update is no_update


def test_footer_save_rejects_inactive_click_and_preserves_other_triggers():
    check = callbacks._save_draft_click_is_real
    kwargs = {
        'modal_clicks': None,
        'footer_clicks': None,
        'workflow_clicks': None,
        'workflow_id': 'manager-workflow-save',
    }
    assert check(SAVE_BUTTON_ID, **{**kwargs, 'footer_clicks': 1})
    assert not check(SAVE_BUTTON_ID, **{**kwargs, 'footer_clicks': 0})
    assert check(MODAL_SAVE_BUTTON_ID, **{**kwargs, 'modal_clicks': 1})
    assert check('manager-workflow-save', **{**kwargs, 'workflow_clicks': 1})


@pytest.mark.parametrize('editor', ('rule', 'message'))
def test_modal_save_closes_editor_only_after_success(monkeypatch, editor):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    revision = callbacks._editor_revision(AlarmConfiguration.from_document(document), current)
    navigation = initial_navigation()
    if editor == 'rule':
        navigation.update(page='family', family_key='family-a', rule_index=0)
    else:
        navigation.update(page='global', tab='messages', message_index=0)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        1, None, None, document, current, revision, navigation
    )

    assert updated == saved
    assert 'Borrador guardado' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update == {**navigation, 'rule_index': None, 'message_index': None}
    assert nav_update['page'] == navigation['page']
    assert nav_update['family_key'] == navigation['family_key']


def test_modal_save_keeps_editor_open_on_stale_revision(monkeypatch):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        1, None, None, document, current, 'stale-revision', navigation
    )

    assert updated is no_update
    assert saved is no_update
    assert 'revision changed' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update is no_update


def test_modal_save_keeps_editor_open_on_validation_error(monkeypatch):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    document['rules'][0]['default_deactivation']['max_duration_hours'] = 13
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    updated, saved, _feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        1, None, None, document, current, None, navigation
    )

    assert updated is no_update
    assert saved is no_update
    assert modal_feedback is not None
    assert nav_update is no_update


def test_workflow_save_does_not_close_open_editor(monkeypatch):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    revision = callbacks._editor_revision(AlarmConfiguration.from_document(document), current)
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id='save-draft-action'))

    updated, saved, feedback, _modal_feedback, nav_update = app.callbacks['save_draft'](
        None, None, 1, document, current, revision, navigation
    )

    assert updated == saved
    assert 'Borrador guardado' in feedback.children
    assert nav_update is no_update



def test_modal_save_keeps_editor_open_without_permission(monkeypatch):
    context, _binding = _context()
    app = CallbackAppStub()
    callbacks.register_alarm_configuration_admin_callbacks(
        app, replace(context, can_manage=lambda: False)
    )
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        1, None, None, configuration().to_document(), None, None, navigation
    )

    assert updated is no_update and saved is no_update
    assert 'permission' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update is no_update


def test_modal_save_keeps_editor_open_when_workspace_write_fails(monkeypatch):
    context, _binding = _context()
    app = CallbackAppStub()

    def failed_write(_draft, _payload):
        raise ManagerProjectionError('Workspace write failed')

    callbacks.register_alarm_configuration_admin_callbacks(
        app, replace(context, workspace_payload_writer=failed_write)
    )
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        1, None, None, configuration().to_document(), None, None, navigation
    )

    assert updated is no_update and saved is no_update
    assert 'Workspace write failed' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update is no_update


def test_inactive_modal_click_does_not_close_editor(monkeypatch):
    app, _binding = _registered_callbacks()
    navigation = {**initial_navigation(), 'page': 'family', 'family_key': 'family-a', 'rule_index': 0}
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=MODAL_SAVE_BUTTON_ID))

    result = app.callbacks['save_draft'](0, None, None, None, None, None, navigation)

    assert result == (no_update,) * 5
