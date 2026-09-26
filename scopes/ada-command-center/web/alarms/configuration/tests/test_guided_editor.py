from dash import html

from ada_command_center.web.alarms.configuration.web.diagnostics import (
    authoring_issues,
    readiness_hints,
)
from ada_command_center.web.alarms.configuration.web.guided_rule import (
    build_rule_section,
    tool_kind,
)
from ada_command_center.web.alarms.configuration.web.ids import STEP_ADD_TYPE
from ada_command_center.web.alarms.configuration.web.labels import field_help, value_label


def test_guided_section_mounts_only_selected_group() -> None:
    groups = [
        html.Fieldset([html.Legend(str(index)), html.Div(id=f'group-{index}')])
        for index in range(7)
    ]
    result = build_rule_section(
        groups,
        section='evaluation',
        criticality='C2',
        targets=[],
        references=None,
    )
    body = result
    content = body.children[1]
    panels = content.children[1]
    assert panels.children == [groups[2]]
    assert len(body.children[0].children) == 4


def test_criticality_three_omits_add_step_without_deleting_existing_data() -> None:
    groups = [html.Fieldset([html.Legend('Sección')]) for _ in range(7)]
    existing = html.Fieldset([html.Legend('Destino previo')])
    groups[5] = html.Section(
        [
            html.H5('Escalamiento'),
            html.Label('Origen'),
            html.Button('Agregar', id={'type': STEP_ADD_TYPE, 'rule': 0}),
            existing,
        ]
    )
    result = build_rule_section(
        groups,
        section='behavior',
        criticality='C3',
        targets=[],
        references=None,
    )
    rendered = result.children[1].children[1].children[-1]
    assert existing in rendered.children
    assert all(
        getattr(item, 'id', None) != {'type': STEP_ADD_TYPE, 'rule': 0}
        for item in rendered.children
    )


def test_visual_target_kind_is_resolved_from_current_reference_document() -> None:
    assert (
        tool_kind({'tools': [{'tool_key': 'mine', 'kind': 'INTEGRATED_OPERATIONS'}]}, 'mine')
        == 'INTEGRATED_OPERATIONS'
    )
    assert tool_kind(None, 'mine') is None


def test_incomplete_rule_reports_fields_and_c3_routing_conflict() -> None:
    issues = authoring_issues(
        {
            'rules': [
                {
                    'identity': {'family_key': 'mina', 'alarm_key': ''},
                    'criticality': 'C3',
                    'escalation': {'origin_tool_key': 'mine', 'steps': [{'is_enabled': True}]},
                }
            ],
            'messages': [],
        }
    )
    assert any('Identificador de alarma' in issue for issue in issues)
    hints = readiness_hints(
        {'rules': [{'criticality': 'C3', 'escalation': {'steps': [{'is_enabled': True}]}}]}
    )
    assert any('C3 no admite pasos habilitados' in hint for hint in hints)
    assert authoring_issues({'rules': [], 'messages': []}) == ()


def test_labels_translate_the_interface_without_changing_contract_values() -> None:
    assert value_label('SAFETY_HEALTH') == 'Seguridad y salud'
    assert value_label('C3').startswith('C3')
    assert field_help('Special conditions') is not None


def test_section_navigation_keeps_current_rule_and_draft(monkeypatch) -> None:
    from types import SimpleNamespace

    from ada_command_center.web.alarms.configuration.web import family_callbacks
    from ada_command_center.web.alarms.configuration.web.authoring import (
        empty_authoring_document,
    )
    from ada_command_center.web.alarms.configuration.web.families import (
        add_rule_in_family,
        initial_navigation,
    )
    from ada_command_center.web.alarms.configuration.web.ids import RULE_SECTION_TYPE

    class Callbacks:
        def __init__(self) -> None:
            self.callbacks = {}

        def callback(self, *_args, **_kwargs):
            def register(callback):
                self.callbacks[callback.__name__] = callback
                return callback

            return register

    app = Callbacks()
    family_callbacks.register_family_callbacks(app)
    document = add_rule_in_family(empty_authoring_document(), 'mina')
    original_key = document['rules'][0]['identity']['alarm_key']
    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mina',
        'tab': 'rules',
        'rule_index': 0,
    }
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': RULE_SECTION_TYPE, 'section': 'visual'},
            triggered=[{'value': 1}],
        ),
    )
    updated = app.callbacks['select_rule_section']([1], navigation, document)
    assert updated['section'] == 'visual'
    assert updated['rule_index'] == 0
    assert document['rules'][0]['identity']['alarm_key'] == original_key
