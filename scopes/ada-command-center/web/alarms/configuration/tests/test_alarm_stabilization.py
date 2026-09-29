from types import SimpleNamespace

from ada_command_center.web.alarms.configuration.web import callbacks
from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.diagnostics import authoring_issues
from ada_command_center.web.alarms.configuration.web.families import (
    add_rule_in_family,
    initial_navigation,
)
from ada_command_center.web.alarms.configuration.web.ids import SAVE_BUTTON_ID
from ada_command_center.web.alarms.configuration.web.pagination import change_list_page, list_page
from ada_command_center.web.alarms.configuration.web.parameters import (
    add_parameter,
    parameter_issues,
    set_parameter_field,
)

from .test_workspace_hydration import _registered_callbacks


def test_parameter_name_survives_type_change_and_localized_float():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_parameter(document, 0)
    document = set_parameter_field(document, 0, 0, 'key', 'text-add')
    document = set_parameter_field(document, 0, 0, 'kind', 'FLOAT')
    document = set_parameter_field(document, 0, 0, 'value', '15,2')
    rule = document['rules'][0]
    assert rule['_parameter_rows'][0] == {'key': 'text-add', 'kind': 'FLOAT', 'value': 15.2}
    assert rule['parameters']['text-add'] == 15.2
    assert not parameter_issues(rule)
    same_kind = set_parameter_field(document, 0, 0, 'kind', 'FLOAT')
    assert same_kind['rules'][0]['parameters']['text-add'] == 15.2
    dotted = set_parameter_field(document, 0, 0, 'value', '15.2')
    assert dotted['rules'][0]['parameters']['text-add'] == 15.2


def test_incomplete_float_remains_visible_as_validation_issue():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_parameter(document, 0)
    document = set_parameter_field(document, 0, 0, 'key', 'threshold')
    document = set_parameter_field(document, 0, 0, 'kind', 'FLOAT')
    document = set_parameter_field(document, 0, 0, 'value', '15,')
    rule = document['rules'][0]
    assert rule['_parameter_rows'][0]['value'] == '15,'
    assert 'threshold' not in rule['parameters']
    assert any('número' in issue for issue in parameter_issues(rule))


def test_deactivation_issue_detected_before_document_serialization():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document['rules'][0]['default_deactivation'] = {
        'enabled': True,
        'max_duration_hours': 13,
        'approval_required': False,
    }
    assert any('invalid deactivation duration limit' in issue for issue in authoring_issues(document))


def test_save_exposes_nested_domain_error_and_does_not_persist_invalid_document(monkeypatch):
    app, _ = _registered_callbacks()
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=SAVE_BUTTON_ID))
    document = {
        'rules': [],
        'messages': [
            {
                'message_key': 'm',
                'scope': 'GLOBAL',
                'family_key': None,
                'display_text': 'text',
                'is_active': True,
                'deactivation_override': {
                    'enabled': False,
                    'max_duration_hours': None,
                    'approval_required': True,
                },
            }
        ],
    }
    updated, saved, feedback, modal_feedback, nav_update = app.callbacks['save_draft'](
        None, 1, None, document, None, None, None
    )
    from dash import no_update

    assert updated is no_update
    assert saved is no_update
    assert 'disabled deactivation' in feedback.children
    assert modal_feedback.children == feedback.children
    assert nav_update is no_update


def test_pagination_keeps_selected_capacity_when_list_contains_fewer_items():
    source = tuple(range(5))
    ten = list_page(source, initial_navigation(), 'rules')
    twenty = list_page(source, change_list_page(initial_navigation(), 'rules', size=20), 'rules')
    assert ten.request.page_size == 10
    assert twenty.request.page_size == 20
    assert ten.items == twenty.items == source
    assert ten.total_count == twenty.total_count == 5
