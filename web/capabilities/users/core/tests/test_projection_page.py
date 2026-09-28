from types import SimpleNamespace

from atlanticus.web.users.web import projection as page


class _App:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(fn):
            self.callbacks[fn.__name__] = fn
            return fn
        return register


class _Workflow:
    def __init__(self):
        self.calls = []
        self.snapshot_ids = ('0123456789abcdef',)

    def history(self):
        return self.snapshot_ids

    def history_details(self):
        return ({'snapshot_id': self.snapshot_ids[0],
                 'saved_at_utc': '2026-09-28T08:45:00+00:00'},)

    def describe_snapshot(self, snapshot_id):
        self.calls.append(('describe', snapshot_id))
        return {'snapshot_id': snapshot_id,
                'captured_at_utc': '2026-09-28T08:44:00+00:00',
                'origin_environment': 'lab', 'approved_count': 1,
                'approval_reference': 'APPROVAL-REF', 'operator_id': 'user-a'}

    def preview_capture(self):
        self.calls.append(('preview',))
        return {'approved_ids': ['one'], 'candidate_ids': ['candidate'], 'digest': 'abcd'}

    def capture(self, preview, reference):
        self.calls.append(('capture', preview, reference))
        return {'snapshot_id': '0123456789abcdef', 'approved_count': 1}

    def inspect(self, snapshot_id):
        self.calls.append(('inspect', snapshot_id))
        return _inspection()

    def apply(self, **kwargs):
        self.calls.append(('apply', kwargs))
        return {'operation_id': 'operation-1', 'created': 1, 'updated': 0, 'deleted': 0}


def _inspection(**overrides):
    content = {
        'snapshot_id': '0123456789abcdef',
        'snapshot_digest': 'digest',
        'origin_environment': 'origin',
        'captured_at_utc': '2026-09-28T00:00:00+00:00',
        'approved_count': 2,
        'registry_state': 'empty',
        'can_restore': True,
        'can_replace': True,
        'create_ids': ['missing-user'],
        'update_ids': [],
        'delete_ids': [],
        'discarded_candidate_ids': [],
        'registry_write_required': True,
        'differences': [{'user_id': 'missing-user', 'kind': 'missing', 'fields': []}],
    }
    content.update(overrides)
    return content


def _callbacks(monkeypatch, *, authorized=True):
    workflow = _Workflow()
    app = _App()
    page.register_users_projection_callbacks(
        app,
        page.UsersProjectionWebContext(workflow=workflow, can_manage=lambda: authorized),
    )
    monkeypatch.setattr(page, 'ctx', SimpleNamespace(triggered_id=None))
    return workflow, app.callbacks


def test_tabs_are_separate_processes(monkeypatch):
    _, callbacks = _callbacks(monkeypatch)
    page.ctx.triggered_id = page._id('apply-tab')
    tab, capture_tab, apply_tab, capture_panel, apply_panel = callbacks['switch_tab'](0, 1, 'capture')
    assert tab == 'apply'
    assert '--active' not in capture_tab
    assert '--active' in apply_tab
    assert '--active' not in capture_panel
    assert '--active' in apply_panel


def test_history_and_inspection_must_be_reselected_after_change(monkeypatch):
    workflow, callbacks = _callbacks(monkeypatch)
    options, error = callbacks['history'](None, None)
    assert len(options) == 1 and error is None
    assert options[0]['value'] == '0123456789abcdef'
    assert 'Guardado: 28/09/2026 08:45 UTC' in options[0]['label']
    summary = callbacks['selected_summary'](options[0]['value'])
    assert 'describe' in workflow.calls[-1]
    assert 'lab' in str(summary)
    workflow.calls.clear()
    page.ctx.triggered_id = page._id('snapshot-select')
    inspection, panel = callbacks['inspect'](0, options[0]['value'], 0, None, None)
    assert inspection is None
    assert workflow.calls == []
    page.ctx.triggered_id = page._id('inspect-button')
    inspection, panel = callbacks['inspect'](1, options[0]['value'], 0, None, None)
    assert inspection['create_ids'] == ['missing-user']
    assert workflow.calls == [('inspect', options[0]['value'])]
    assert callbacks['inspect_ready'](None)
    assert not callbacks['inspect_ready'](options[0]['value'])


def test_capture_requires_preview_reference_and_modal_approval(monkeypatch):
    workflow, callbacks = _callbacks(monkeypatch)
    preview, _ = callbacks['preview_capture'](1)
    assert callbacks['capture_ready'](preview, '')
    assert not callbacks['capture_ready'](preview, ' TICKET-1 ')
    page.ctx.triggered_id = page._id('open-capture')
    shown = callbacks['modal'](1, 0, 0, 0, 0, preview, 'TICKET-1', None, None, None, None)
    assert '--open' in shown[0]
    assert shown[4]['action'] == 'capture'
    result = callbacks['confirm'](1, shown[4], [])
    assert result[0] == page._CLOSED
    assert result[5] == '0123456789abcdef'
    assert workflow.calls[-1] == ('capture', preview, 'TICKET-1')
    assert result[8] == ''
    assert callbacks['capture_ready'](None, '')


def test_projection_requires_inspection_explicit_modal_and_human_reviews(monkeypatch):
    workflow, callbacks = _callbacks(monkeypatch)
    state = _inspection()
    choices, selected = callbacks['modes'](state, 'restore')
    assert selected == 'restore'
    assert all(not option['disabled'] for option in choices)
    message, disabled = callbacks['apply_ready']('restore', state, state['snapshot_id'], '')
    assert disabled
    message, disabled = callbacks['apply_ready']('restore', state, state['snapshot_id'], 'TICKET-2')
    assert not disabled
    page.ctx.triggered_id = page._id('open-apply')
    shown = callbacks['modal'](0, 1, 0, 0, 0, None, None,
                               state, state['snapshot_id'], 'restore', 'TICKET-2')
    assert '--open' in shown[0]
    assert shown[4]['action'] == 'apply'
    assert {option['value'] for option in shown[5]} == {'maintenance', 'revocations'}
    denied = callbacks['confirm'](1, shown[4], ['maintenance'])
    assert denied[0] is page.no_update
    assert workflow.calls == []
    approved = callbacks['confirm'](2, shown[4], ['maintenance', 'revocations'])
    assert approved[0] == page._CLOSED
    assert workflow.calls[-1][1]['confirmed'] is True
    assert workflow.calls[-1][1]['mode'] == 'restore'
    assert approved[7] == 'operation-1'


def test_blocked_modes_and_aligned_state_disable_actions(monkeypatch):
    _, callbacks = _callbacks(monkeypatch)
    different = _inspection(can_restore=False, can_replace=True)
    choices, selected = callbacks['modes'](different, 'restore')
    assert selected == 'replace'
    assert choices[0]['disabled']
    message, disabled = callbacks['apply_ready'](
        'restore', different, different['snapshot_id'], 'TICKET-1'
    )
    assert disabled and 'bloqueada' in message
    aligned = _inspection(
        create_ids=[], update_ids=[], delete_ids=[], registry_write_required=False, differences=[]
    )
    choices, selected = callbacks['modes'](aligned, 'replace')
    assert all(option['disabled'] for option in choices)
    message, disabled = callbacks['apply_ready']('restore', aligned, aligned['snapshot_id'], 'T')
    assert disabled and 'coinciden' in message


def test_server_side_authorization_does_not_trust_disabled_buttons(monkeypatch):
    workflow, callbacks = _callbacks(monkeypatch, authorized=False)
    assert callbacks['capture_ready']({'approved_ids': ['one']}, 'TICKET-1')
    assert callbacks['inspect_ready']('0123456789abcdef')
    page.ctx.triggered_id = page._id('open-apply')
    result = callbacks['modal'](0, 1, 0, 0, 0, None, None,
                                _inspection(), '0123456789abcdef', 'replace', 'TICKET-1')
    assert result[4] is None
    result = callbacks['confirm'](1, {'action': 'apply'}, ['maintenance', 'revocations'])
    assert result[0] == page._CLOSED
    assert workflow.calls == []


def test_complete_substitution_is_distinct_and_needs_modal_review(monkeypatch):
    workflow, callbacks = _callbacks(monkeypatch)
    state = _inspection(
        can_restore=False,
        update_ids=['updated'],
        delete_ids=['unexpected'],
        discarded_candidate_ids=['pending'],
    )
    choices, selected = callbacks['modes'](state, 'restore')
    assert selected == 'replace'
    assert choices[0]['disabled'] and not choices[1]['disabled']
    page.ctx.triggered_id = page._id('open-apply')
    opened = callbacks['modal'](
        0, 1, 0, 0, 0, None, None,
        state, state['snapshot_id'], 'replace', 'TICKET-3',
    )
    assert opened[4]['mode'] == 'replace'
    assert 'sustitución' in opened[1].lower()
    approved = callbacks['confirm'](1, opened[4], ['maintenance', 'revocations'])
    assert approved[0] == page._CLOSED
    assert workflow.calls[-1][1]['mode'] == 'replace'
    assert workflow.calls[-1][1]['confirmed'] is True


def test_history_fallback_without_blob_date():
    assert page._snapshot_option({'snapshot_id': '0123456789abcdef',
                                  'saved_at_utc': None}).startswith('Fecha no disponible')
