from types import SimpleNamespace

from dash import no_update

from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.web.alarms.configuration.web import callbacks
from ada_command_center.web.alarms.configuration.web.ids import (
    MODAL_SAVE_BUTTON_ID,
    SAVE_BUTTON_ID,
)
from atlanticus.web.manager.workspace import ManagerWorkspace

from .helpers import configuration
from .test_workspace_hydration import _registered_callbacks


def test_footer_save_persists_the_current_manager_workspace(monkeypatch):
    app, binding = _registered_callbacks()
    current = binding.save_payload(None, configuration().to_document())
    document = binding.load_payload(current)
    revision = callbacks._editor_revision(AlarmConfiguration.from_document(document), current)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=SAVE_BUTTON_ID))

    updated, saved, feedback, modal_feedback = app.callbacks['save_draft'](
        None, 1, None, document, current, revision
    )

    assert updated is not no_update
    assert updated == saved
    assert AlarmConfiguration.from_document(
        dict(ManagerWorkspace.from_document(updated).payload)
    ) == AlarmConfiguration.from_document(document)
    assert 'Borrador guardado' in feedback.children
    assert modal_feedback.children == feedback.children


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
