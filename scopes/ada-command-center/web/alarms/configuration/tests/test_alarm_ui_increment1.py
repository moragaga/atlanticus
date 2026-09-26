from ada_command_center.web.alarms.configuration.web.authoring import empty_authoring_document
from ada_command_center.web.alarms.configuration.web.families import (
    add_message_in_family,
    add_rule_in_family,
    initial_navigation,
)
from ada_command_center.web.alarms.configuration.web.family_panel import build_active_editor
from ada_command_center.web.alarms.configuration.web.pagination import list_page, list_pagination


def test_only_selected_rule_is_sent_to_editor():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_rule_in_family(document, 'mine')
    seen = []

    def rule_editor(index, *_args):
        seen.append(index)
        return 'selected rule'

    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mine',
        'rule_index': 1,
    }
    title, detail = build_active_editor(
        document,
        None,
        navigation,
        rule_editor=rule_editor,
        message_editor=lambda *_args: 'unexpected message',
    )
    assert (title, detail) == ('Editar regla', 'selected rule')
    assert seen == [1]


def test_global_message_editor_is_only_opened_from_global_context():
    document = add_message_in_family(empty_authoring_document(), None)
    document = add_message_in_family(document, 'mine')
    seen = []

    def message_editor(index, *_args):
        seen.append(index)
        return 'selected message'

    title, detail = build_active_editor(
        document,
        None,
        {**initial_navigation(), 'page': 'global', 'message_index': 1},
        rule_editor=lambda *_args: 'unexpected rule',
        message_editor=message_editor,
    )
    assert (title, detail) == ('', None)
    assert seen == []

    title, detail = build_active_editor(
        document,
        None,
        {**initial_navigation(), 'page': 'global', 'message_index': 0},
        rule_editor=lambda *_args: 'unexpected rule',
        message_editor=message_editor,
    )
    assert (title, detail) == ('Editar mensaje', 'selected message')
    assert seen == [0]


def test_small_list_hides_redundant_page_controls():
    page = list_page(tuple(range(3)), initial_navigation(), 'families')
    assert list_pagination(page, 'families') is None
