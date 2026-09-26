from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.diagnostics import authoring_issues
from ada_command_center.web.alarms.configuration.web.families import add_rule_in_family
from ada_command_center.web.alarms.configuration.web.parameters import (
    add_parameter,
    parameter_issues,
    parameter_rows,
    remove_parameter,
    set_parameter_field,
)


def _document():
    return add_rule_in_family(empty_authoring_document(), 'mina')


def test_parameter_builder_preserves_contract_and_original_document():
    initial = _document()
    added = add_parameter(initial, 0)
    assert initial['rules'][0]['parameters'] == {}
    assert parameter_issues(added['rules'][0])
    renamed = set_parameter_field(added, 0, 0, 'key', 'threshold')
    typed = set_parameter_field(renamed, 0, 0, 'kind', 'FLOAT')
    assert parameter_issues(typed['rules'][0])
    complete = set_parameter_field(typed, 0, 0, 'value', 17)
    assert complete['rules'][0]['parameters'] == {'threshold': 17.0}
    assert parameter_issues(complete['rules'][0]) == ()
    assert parameter_rows(complete['rules'][0])[0]['kind'] == 'FLOAT'
    assert added['rules'][0]['parameters'] == {}


def test_boolean_and_text_are_typed_and_remove_without_legacy_json():
    current = add_parameter(_document(), 0)
    current = set_parameter_field(current, 0, 0, 'key', 'enabled')
    current = set_parameter_field(current, 0, 0, 'kind', 'BOOLEAN')
    current = set_parameter_field(current, 0, 0, 'value', False)
    current = add_parameter(current, 0)
    current = set_parameter_field(current, 0, 1, 'key', 'window')
    current = set_parameter_field(current, 0, 1, 'value', '15m')
    assert current['rules'][0]['parameters'] == {'enabled': False, 'window': '15m'}
    removed = remove_parameter(current, 0, 0)
    assert removed['rules'][0]['parameters'] == {'window': '15m'}
    assert parameter_rows(removed['rules'][0]) == [
        {'key': 'window', 'kind': 'TEXT', 'value': '15m'}
    ]


def test_incomplete_parameter_has_visible_error_before_draft_save():
    current = add_parameter(_document(), 0)
    assert any('nombre técnico' in issue for issue in parameter_issues(current['rules'][0]))
    assert any('parámetro' in issue.lower() for issue in authoring_issues(current))
    current = set_parameter_field(current, 0, 0, 'key', 'x')
    current = add_parameter(current, 0)
    duplicate = set_parameter_field(current, 0, 1, 'key', 'x')
    assert any('repetido' in issue for issue in parameter_issues(duplicate['rules'][0]))
    assert duplicate['rules'][0]['parameters'] == {'x': ''}
