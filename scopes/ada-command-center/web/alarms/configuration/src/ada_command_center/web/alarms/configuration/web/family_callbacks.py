from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada_command_center.web.alarms.configuration.web.authoring import (
    empty_authoring_document,
)
from ada_command_center.web.alarms.configuration.web.families import (
    add_message_in_family,
    add_rule_in_family,
    family_catalog,
    initial_navigation,
    require_new_family_key,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.guided_rule import RULE_SECTIONS
from ada_command_center.web.alarms.configuration.web.ids import (
    ADD_MESSAGE_BUTTON_ID,
    ADD_RULE_BUTTON_ID,
    AUTHORING_STORE_ID,
    CREATE_FAMILY_MESSAGE_ID,
    CREATE_FAMILY_RULE_ID,
    FAMILY_ACTION_RESULT_ID,
    FAMILY_CREATE_PANEL_ID,
    FAMILY_NAV_STORE_ID,
    FAMILY_NEW_KEY_ID,
    FAMILY_SELECT_TYPE,
    FAMILY_TAB_TYPE,
    MESSAGE_SELECT_TYPE,
    RULE_SECTION_TYPE,
    RULE_SELECT_TYPE,
    SHOW_FAMILIES_ID,
    SHOW_GLOBAL_MESSAGES_ID,
)


def register_family_callbacks(app: object) -> None:
    @app.callback(
        Output(FAMILY_NAV_STORE_ID, 'data'),
        Input(SHOW_FAMILIES_ID, 'n_clicks'),
        Input(SHOW_GLOBAL_MESSAGES_ID, 'n_clicks'),
        Input({'type': FAMILY_SELECT_TYPE, 'index': ALL}, 'n_clicks'),
        Input({'type': FAMILY_TAB_TYPE, 'tab': ALL}, 'n_clicks'),
        Input({'type': RULE_SELECT_TYPE, 'index': ALL}, 'n_clicks'),
        Input({'type': MESSAGE_SELECT_TYPE, 'index': ALL}, 'n_clicks'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def navigate(
        _families_clicks,
        _global_clicks,
        _family_clicks,
        _tab_clicks,
        _rule_clicks,
        _message_clicks,
        current_nav,
        document,
    ):
        trigger = ctx.triggered_id
        if not _real_click():
            return no_update
        current = current_nav if isinstance(current_nav, dict) else initial_navigation()
        catalog = family_catalog(document)
        if trigger == SHOW_FAMILIES_ID:
            return initial_navigation()
        if trigger == SHOW_GLOBAL_MESSAGES_ID:
            return {**initial_navigation(), 'page': 'global', 'tab': 'messages'}
        if not isinstance(trigger, dict):
            return no_update
        kind = trigger.get('type')
        if kind == FAMILY_SELECT_TYPE:
            index = trigger.get('index')
            if type(index) is not int or not 0 <= index < len(catalog.families):
                return no_update
            return {
                **initial_navigation(),
                'page': 'family',
                'family_key': catalog.families[index].key,
            }
        if kind == FAMILY_TAB_TYPE:
            if selected_family(current, document) is None:
                return no_update
            tab = trigger.get('tab')
            if tab not in {'rules', 'messages'}:
                return no_update
            return {**current, 'tab': tab}
        if kind == RULE_SELECT_TYPE:
            key = selected_family(current, document)
            group = catalog.get(key) if key is not None else None
            index = trigger.get('index')
            if group is None or type(index) is not int or index not in group.rule_indexes:
                return no_update
            return {**current, 'tab': 'rules', 'rule_index': index, 'section': 'general'}
        if kind == MESSAGE_SELECT_TYPE:
            if current.get('page') == 'global':
                indexes = catalog.global_message_indexes
            else:
                key = selected_family(current, document)
                group = catalog.get(key) if key is not None else None
                indexes = group.message_indexes if group is not None else ()
            index = trigger.get('index')
            if type(index) is not int or index not in indexes:
                return no_update
            return {**current, 'tab': 'messages', 'message_index': index}
        return no_update

    @app.callback(
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Input(ADD_RULE_BUTTON_ID, 'n_clicks'),
        Input(ADD_MESSAGE_BUTTON_ID, 'n_clicks'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_family_item(_rule_clicks, _message_clicks, current_nav, document):
        if not _real_click() or not isinstance(document, dict):
            return no_update, no_update
        current = current_nav if isinstance(current_nav, dict) else initial_navigation()
        trigger = ctx.triggered_id
        family = selected_family(current, document)
        if trigger == ADD_RULE_BUTTON_ID and family:
            rules = document.get('rules')
            index = len(rules) if isinstance(rules, list) else 0
            return add_rule_in_family(document, family), {
                **current,
                'tab': 'rules',
                'rule_index': index,
                'message_index': None,
                'section': 'general',
            }
        if trigger == ADD_MESSAGE_BUTTON_ID:
            if current.get('page') != 'global' and not family:
                return no_update, no_update
            messages = document.get('messages')
            index = len(messages) if isinstance(messages, list) else 0
            key = None if current.get('page') == 'global' else family
            return add_message_in_family(document, key), {
                **current,
                'tab': 'messages',
                'message_index': index,
                'rule_index': None,
            }
        return no_update, no_update

    @app.callback(
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Output(FAMILY_ACTION_RESULT_ID, 'children'),
        Input(CREATE_FAMILY_RULE_ID, 'n_clicks'),
        Input(CREATE_FAMILY_MESSAGE_ID, 'n_clicks'),
        State(FAMILY_NEW_KEY_ID, 'value'),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def create_family(_rule_clicks, _message_clicks, raw_key, document):
        if not _real_click() or ctx.triggered_id not in {
            CREATE_FAMILY_RULE_ID,
            CREATE_FAMILY_MESSAGE_ID,
        }:
            return no_update, no_update, no_update
        current = document if isinstance(document, dict) else empty_authoring_document()
        try:
            key = require_new_family_key(current, raw_key)
            navigation = {**initial_navigation(), 'page': 'family', 'family_key': key}
            if ctx.triggered_id == CREATE_FAMILY_RULE_ID:
                rules = current.get('rules')
                index = len(rules) if isinstance(rules, list) else 0
                updated = add_rule_in_family(current, key)
                navigation.update(rule_index=index, section='general')
            else:
                messages = current.get('messages')
                index = len(messages) if isinstance(messages, list) else 0
                updated = add_message_in_family(current, key)
                navigation.update(tab='messages', message_index=index)
        except ValueError as error:
            message = {
                'Family key must not be empty': 'Ingresa una clave para la familia.',
                'Family key must not have leading or trailing whitespace': (
                    'La clave no debe tener espacios al principio ni al final.'
                ),
                'Family key already exists': 'La familia ya existe; selecciónala para continuar.',
            }.get(str(error), 'No fue posible crear la familia.')
            return no_update, no_update, html.Span(message)
        return (
            updated,
            navigation,
            html.Span('Completa el primer elemento para guardar la familia.'),
        )

    @app.callback(
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': RULE_SECTION_TYPE, 'section': ALL}, 'n_clicks'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def select_rule_section(_clicks, navigation, document):
        trigger = ctx.triggered_id
        if not _real_click() or not isinstance(trigger, dict):
            return no_update
        section = trigger.get('section')
        if section not in {entry[0] for entry in RULE_SECTIONS}:
            return no_update
        family = selected_family(navigation, document)
        group = family_catalog(document).get(family) if family else None
        if group is None or navigation.get('rule_index') not in group.rule_indexes:
            return no_update
        return {**navigation, 'section': section}

    @app.callback(
        Output(FAMILY_CREATE_PANEL_ID, 'hidden'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
    )
    def show_family_creation(navigation):
        return not isinstance(navigation, dict) or navigation.get('page') != 'families'

    @app.callback(
        Output(ADD_RULE_BUTTON_ID, 'disabled'),
        Output(ADD_MESSAGE_BUTTON_ID, 'disabled'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
        Input(AUTHORING_STORE_ID, 'data'),
    )
    def update_add_controls(navigation, document):
        family = selected_family(navigation, document)
        global_messages = isinstance(navigation, dict) and navigation.get('page') == 'global'
        return not bool(family), not bool(family) and not global_messages


def _real_click() -> bool:
    if not ctx.triggered:
        return False
    value = ctx.triggered[0].get('value')
    return type(value) is int and value > 0
