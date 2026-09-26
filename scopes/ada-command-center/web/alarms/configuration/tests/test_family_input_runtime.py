from dash import dcc

from ada_command_center.web.alarms.configuration.web.ids import FAMILY_NEW_KEY_ID
from ada_command_center.web.alarms.configuration.web.layout import (
    build_alarm_configuration_admin,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)


def _visit(component):
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _visit(item)
        return
    if component is None:
        return
    yield component
    if hasattr(component, 'children'):
        yield from _visit(component.children)


def test_visitor_includes_leaf_inputs():
    field = dcc.Input(id=FAMILY_NEW_KEY_ID, type='text')
    assert list(_visit([field])) == [field]


def test_manager_layout_renders_family_form_with_live_value():
    context = AlarmConfigurationAdminWebContext(
        workspace_payload_reader=lambda value: value,
        workspace_payload_writer=lambda _original, updated: updated,
        draft_store_id='draft',
        saved_draft_store_id='saved',
        draft_save_action_id='save',
        editor_revision_store_id='revision',
    )
    layout = build_alarm_configuration_admin(context)
    fields = []
    for element in _visit(layout):
        if getattr(element, 'id', None) == FAMILY_NEW_KEY_ID:
            fields.append(element)
    assert len(fields) == 1
    field = fields[0]
    assert isinstance(field, dcc.Input)
    assert field.value == ''
    assert field.debounce is False
    assert field.type == 'text'
