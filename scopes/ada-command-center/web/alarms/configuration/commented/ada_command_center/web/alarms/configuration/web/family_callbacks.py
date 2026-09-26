# La navegación y la paginación conservan el contexto y el borrador entre páginas.
# Estructura y comportamiento idénticos al módulo productivo.

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
    merged_family_catalog,
    require_new_family_key,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.guided_rule import RULE_SECTIONS
from ada_command_center.web.alarms.configuration.web.ids import (
    ADD_MESSAGE_BUTTON_ID,
    ADD_RULE_BUTTON_ID,
    AUTHORING_STORE_ID,
    CANCEL_FAMILY_CREATE_FOOTER_ID,
    CANCEL_FAMILY_CREATE_ID,
    CLOSE_EDITOR_ID,
    CREATE_FAMILY_ID,
    FAMILY_ACTION_RESULT_ID,
    FAMILY_CREATE_PANEL_ID,
    FAMILY_NAV_STORE_ID,
    FAMILY_NEW_KEY_ID,
    FAMILY_SELECT_TYPE,
    FAMILY_TAB_TYPE,
    LIST_PAGE_SIZE_TYPE,
    LIST_PAGE_TYPE,
    MESSAGE_SELECT_TYPE,
    MODAL_BACK_ID,
    OPEN_FAMILY_CREATE_ID,
    RULE_SECTION_TYPE,
    RULE_SELECT_TYPE,
    SHOW_FAMILIES_ID,
    SHOW_GLOBAL_MESSAGES_ID,
)
from ada_command_center.web.alarms.configuration.web.pagination import change_list_page


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
        if not _real_click():
            return no_update
        current = current_nav if isinstance(current_nav, dict) else initial_navigation()
        trigger = ctx.triggered_id
        catalog = merged_family_catalog(document, current)
        if trigger == SHOW_FAMILIES_ID:
            return _base_navigation(current)
        if trigger == SHOW_GLOBAL_MESSAGES_ID:
            return {**_base_navigation(current), 'page': 'global', 'tab': 'messages'}
        if not isinstance(trigger, dict):
            return no_update
        kind = trigger.get('type')
        if kind == FAMILY_SELECT_TYPE:
            index = trigger.get('index')
            if type(index) is not int or not 0 <= index < len(catalog.families):
                return no_update
            return {
                **_base_navigation(current),
                'page': 'family',
                'family_key': catalog.families[index].key,
            }
        if kind == FAMILY_TAB_TYPE:
            if selected_family(current, document) is None:
                return no_update
            tab = trigger.get('tab')
            if tab not in {'rules', 'messages'}:
                return no_update
            return {**current, 'tab': tab, 'rule_index': None, 'message_index': None}
        if kind == RULE_SELECT_TYPE:
            family = selected_family(current, document)
            group = catalog.get(family) if family is not None else None
            index = trigger.get('index')
            if group is None or type(index) is not int or index not in group.rule_indexes:
                return no_update
            return {**current, 'tab': 'rules', 'rule_index': index, 'section': 'general'}
        if kind == MESSAGE_SELECT_TYPE:
            if current.get('page') == 'global':
                indexes = catalog.global_message_indexes
            else:
                family = selected_family(current, document)
                group = catalog.get(family) if family is not None else None
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
        family = selected_family(current, document)
        trigger = ctx.triggered_id
        pending = _pending_families(current)
        if trigger == ADD_RULE_BUTTON_ID and family:
            rules = document.get('rules')
            index = len(rules) if isinstance(rules, list) else 0
            return add_rule_in_family(document, family), {
                **current,
                'pending_families': [key for key in pending if key != family],
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
                'pending_families': [item for item in pending if item != key],
                'tab': 'messages',
                'message_index': index,
                'rule_index': None,
            }
        return no_update, no_update

    @app.callback(
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Output(FAMILY_ACTION_RESULT_ID, 'children'),
        Output(FAMILY_NEW_KEY_ID, 'value'),
        Input(CREATE_FAMILY_ID, 'n_clicks'),
        State(FAMILY_NEW_KEY_ID, 'value'),
        State(AUTHORING_STORE_ID, 'data'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def create_family(_clicks, raw_key, document, current_nav):
        if not _real_click() or ctx.triggered_id != CREATE_FAMILY_ID:
            return no_update, no_update, no_update
        current = current_nav if isinstance(current_nav, dict) else initial_navigation()
        payload = document if isinstance(document, dict) else empty_authoring_document()
        pending = _pending_families(current)
        try:
            key = require_new_family_key(payload, raw_key, pending=pending)
        except ValueError as error:
            message = {
                'Family key must not be empty': 'Indica un nombre para la familia.',
                'Family key must not have leading or trailing whitespace': (
                    'Elimina los espacios al principio o al final.'
                ),
                'Family key already exists': 'Esta familia ya existe. Selecciónala en la lista.',
            }.get(str(error), 'No se pudo crear la familia.')
            return no_update, html.Span(message, role='alert'), no_update
        return (
            {
                **_base_navigation(current),
                'pending_families': [*pending, key],
                'page': 'family',
                'family_key': key,
            },
            html.Span(
                'Familia preparada. Agrega una regla o un mensaje para incorporarla al borrador.',
                role='status',
            ),
            '',
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
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Input(CLOSE_EDITOR_ID, 'n_clicks'),
        Input(MODAL_BACK_ID, 'n_clicks'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def close_editor(_clicks, _back_clicks, navigation):
        if not _real_click() or not isinstance(navigation, dict):
            return no_update
        return {**navigation, 'rule_index': None, 'message_index': None}

    @app.callback(
        Output(FAMILY_CREATE_PANEL_ID, 'hidden'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
    )
    def show_family_creation(navigation):
        return (
            not isinstance(navigation, dict)
            or navigation.get('page') != 'families'
            or not navigation.get('family_create_open', False)
        )

    @app.callback(
        Output(ADD_RULE_BUTTON_ID, 'disabled'),
        Output(ADD_MESSAGE_BUTTON_ID, 'disabled'),
        Output(OPEN_FAMILY_CREATE_ID, 'disabled'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
        Input(AUTHORING_STORE_ID, 'data'),
    )
    def update_add_controls(navigation, document):
        family = selected_family(navigation, document)
        global_messages = isinstance(navigation, dict) and navigation.get('page') == 'global'
        listing = isinstance(navigation, dict) and navigation.get('page') == 'families'
        return not bool(family), not bool(family) and not global_messages, not listing

    @app.callback(
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': LIST_PAGE_TYPE, 'listing': ALL, 'page': ALL, 'action': ALL}, 'n_clicks'),
        Input({'type': LIST_PAGE_SIZE_TYPE, 'listing': ALL, 'size': ALL}, 'value'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def change_pagination(_page_clicks, _size_values, navigation):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered:
            return no_update
        current = navigation if isinstance(navigation, dict) else initial_navigation()
        try:
            if trigger.get('type') == LIST_PAGE_TYPE:
                if not _real_click():
                    return no_update
                return change_list_page(current, trigger.get('listing'), page=trigger.get('page'))
            if trigger.get('type') == LIST_PAGE_SIZE_TYPE:
                size = ctx.triggered[0].get('value')
                if type(size) is not int:
                    return no_update
                existing = current.get('pagination', {})
                item = (
                    existing.get(trigger.get('listing'), {}) if isinstance(existing, dict) else {}
                )
                if isinstance(item, dict) and item.get('size', 10) == size:
                    return no_update
                return change_list_page(current, trigger.get('listing'), size=size)
        except ValueError:
            pass
        return no_update

    @app.callback(
        Output(FAMILY_NAV_STORE_ID, 'data', allow_duplicate=True),
        Input(OPEN_FAMILY_CREATE_ID, 'n_clicks'),
        Input(CANCEL_FAMILY_CREATE_ID, 'n_clicks'),
        Input(CANCEL_FAMILY_CREATE_FOOTER_ID, 'n_clicks'),
        State(FAMILY_NAV_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def toggle_family_creation(_open_clicks, _cancel_clicks, _footer_clicks, navigation):
        if not _real_click():
            return no_update
        current = navigation if isinstance(navigation, dict) else initial_navigation()
        if ctx.triggered_id == OPEN_FAMILY_CREATE_ID and current.get('page') == 'families':
            return {**current, 'family_create_open': True}
        if ctx.triggered_id in {CANCEL_FAMILY_CREATE_ID, CANCEL_FAMILY_CREATE_FOOTER_ID}:
            return {**current, 'family_create_open': False}
        return no_update


def _pending_families(navigation: dict[str, object]) -> list[str]:
    raw = navigation.get('pending_families')
    return [key for key in raw if isinstance(key, str)] if isinstance(raw, list) else []


def _base_navigation(current: dict[str, object]) -> dict[str, object]:
    return {
        **initial_navigation(),
        'pending_families': _pending_families(current),
        'pagination': current.get('pagination', {}),
    }


def _real_click() -> bool:
    if not ctx.triggered:
        return False
    value = ctx.triggered[0].get('value')
    return type(value) is int and value > 0
