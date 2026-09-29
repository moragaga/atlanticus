from __future__ import annotations

from types import SimpleNamespace

from dash import html, no_update

from ada.web.application.configuration_manager import operational_callbacks, operational_ids as ids
from ada.web.application.configuration_manager.operational_layout import modal_class


class FakeApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(fn):
            self.callbacks[fn.__name__] = fn
            return fn

        return register


def test_published_position_closes_modal_but_failed_save_keeps_it_open():
    app = FakeApp()
    operational_callbacks.register_operational_callbacks(app, object())
    close = app.callbacks['close_position_after_publication']
    assert close('release-id') == modal_class(False)
    assert close(None) is no_update


def test_assignment_completion_handles_dash_serialization_without_closing_on_errors():
    app = FakeApp()
    operational_callbacks.register_operational_callbacks(app, object())
    finish = app.callbacks['finish_assignment_operation']
    error = {'props': {'className': 'ada-operational-admin__result--error'}}
    assert finish(error) == (no_update, no_update)
    saved = html.P('Guardado', className='ada-operational-admin__result--success')
    assert finish(saved) == (modal_class(False), saved)
    warning = {
        'type': 'P',
        'props': {
            'children': 'Source durable; projection pending',
            'className': 'ada-operational-admin__result ada-operational-admin__result--warning',
        },
    }
    assert finish(warning) == (modal_class(False), warning)
    assert finish(None) == (no_update, no_update)


def test_modal_open_clears_stale_feedback_but_cancel_does_not_commit(monkeypatch):
    app = FakeApp()
    operational_callbacks.register_operational_callbacks(
        app, SimpleNamespace(can_manage=lambda: True)
    )
    selected = SimpleNamespace(triggered_id=ids.POSITION_NEW)
    monkeypatch.setattr(operational_callbacks, 'ctx', selected)
    assert app.callbacks['open_position']([], 1, 0, 0, 0, []) == (None, modal_class(True), None)
    selected.triggered_id = ids.POSITION_MODAL_CANCEL
    result = app.callbacks['open_position']([], 0, 1, 0, 0, [])
    assert result == (no_update, modal_class(False), no_update)
