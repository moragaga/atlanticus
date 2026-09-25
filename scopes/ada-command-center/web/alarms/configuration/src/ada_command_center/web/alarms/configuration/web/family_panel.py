from __future__ import annotations

from collections.abc import Callable

from dash import html

from ada_command_center.web.alarms.configuration.web.families import (
    FamilySummary,
    merged_family_catalog,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    CLOSE_EDITOR_ID,
    FAMILY_SELECT_TYPE,
    FAMILY_TAB_TYPE,
    MESSAGE_SELECT_TYPE,
    RULE_SELECT_TYPE,
)
from ada_command_center.web.alarms.configuration.web.labels import value_label


def build_family_panel(
    document: dict[str, object],
    references: dict[str, object] | None,
    navigation: dict[str, object] | None,
    *,
    rule_editor: Callable[..., object],
    message_editor: Callable[..., object],
) -> object:
    current = navigation if isinstance(navigation, dict) else {}
    catalog = merged_family_catalog(document, current)
    pending = current.get('pending_families')
    pending_keys = pending if isinstance(pending, list) else []
    if current.get('page') == 'global':
        return _global_messages(catalog.global_message_indexes, document, current, message_editor)
    key = selected_family(current, document)
    if key is None:
        return _family_listing(catalog.families, len(catalog.global_message_indexes), pending_keys)
    family = catalog.get(key)
    if family is None:
        return _family_listing(catalog.families, len(catalog.global_message_indexes), pending_keys)
    return _family_content(family, document, references, current, rule_editor, message_editor)


def _family_listing(
    families: tuple[FamilySummary, ...], global_count: int, pending: list[str]
) -> object:
    cards = [
        html.Button(
            [
                html.Strong(family.key),
                html.Small(
                    'Pendiente · agrega una regla o mensaje'
                    if family.key in pending
                    and not family.rule_indexes
                    and not family.message_indexes
                    else f'{len(family.rule_indexes)} reglas · {len(family.message_indexes)} mensajes'
                ),
                html.Span('Administrar', className='alarm-family__card-action'),
            ],
            id={'type': FAMILY_SELECT_TYPE, 'index': index},
            n_clicks=0,
            className='alarm-family__card',
            type='button',
        )
        for index, family in enumerate(families)
    ]
    return html.Section(
        [
            html.Div(
                [
                    html.H4('Familias'),
                    html.P('Selecciona una familia para administrar sus reglas y mensajes.'),
                ],
                className='alarm-family__heading',
            ),
            html.Div(cards, className='alarm-family__cards')
            if cards
            else html.P('Todavía no existen familias. Crea una para comenzar.'),
            html.P(f'Mensajes globales: {global_count}', className='alarm-family__note'),
        ],
        className='alarm-family__section',
    )


def _family_content(
    family: FamilySummary,
    document: dict[str, object],
    references: dict[str, object] | None,
    navigation: dict[str, object],
    rule_editor: Callable[..., object],
    message_editor: Callable[..., object],
) -> object:
    tab = navigation.get('tab')
    current_tab = tab if tab in {'rules', 'messages'} else 'rules'
    tabs = html.Div(
        [
            html.Button(
                f'Reglas ({len(family.rule_indexes)})',
                id={'type': FAMILY_TAB_TYPE, 'tab': 'rules'},
                n_clicks=0,
                className=_tab_class(current_tab == 'rules'),
                type='button',
            ),
            html.Button(
                f'Mensajes ({len(family.message_indexes)})',
                id={'type': FAMILY_TAB_TYPE, 'tab': 'messages'},
                n_clicks=0,
                className=_tab_class(current_tab == 'messages'),
                type='button',
            ),
        ],
        className='alarm-family__tabs',
    )
    content = (
        _rule_list(family.rule_indexes, document, references, navigation, rule_editor)
        if current_tab == 'rules'
        else _message_list(family.message_indexes, document, navigation, message_editor)
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H4(family.key),
                            html.Small('La familia no se edita desde las reglas.'),
                        ],
                        className='alarm-family__title',
                    ),
                    tabs,
                ],
                className='alarm-family__heading',
            ),
            content,
            html.P(
                'Esta familia está pendiente: se incorpora al documento cuando agregues '
                'su primera regla o mensaje.',
                className='alarm-family__notice',
            )
            if not family.rule_indexes and not family.message_indexes
            else None,
        ],
        className='alarm-family__section',
    )


def _global_messages(
    indexes: tuple[int, ...],
    document: dict[str, object],
    navigation: dict[str, object],
    message_editor: Callable[..., object],
) -> object:
    return html.Section(
        [
            html.H4(f'Mensajes globales ({len(indexes)})'),
            html.P('Estos mensajes pueden utilizarse desde cualquier familia.'),
            _message_list(indexes, document, navigation, message_editor),
        ],
        className='alarm-family__section',
    )


def _rule_list(
    indexes: tuple[int, ...],
    document: dict[str, object],
    references: dict[str, object] | None,
    navigation: dict[str, object],
    rule_editor: Callable[..., object],
) -> object:
    rules = document.get('rules')
    messages = document.get('messages')
    all_rules = rules if isinstance(rules, list) else []
    all_messages = messages if isinstance(messages, list) else []
    chosen = navigation.get('rule_index')
    current = chosen if type(chosen) is int and chosen in indexes else None
    items = [
        html.Button(
            [
                html.Strong(_rule_title(all_rules[index])),
                html.Small(_rule_subtitle(all_rules[index])),
            ],
            id={'type': RULE_SELECT_TYPE, 'index': index},
            n_clicks=0,
            type='button',
            className=_item_class(current == index),
        )
        for index in indexes
    ]
    details = (
        rule_editor(
            current,
            all_rules[current],
            all_rules,
            all_messages,
            references,
            navigation.get('section', 'general'),
        )
        if current is not None
        else None
    )
    return _split_editor(items, details, empty='Esta familia todavía no tiene reglas.')


def _message_list(
    indexes: tuple[int, ...],
    document: dict[str, object],
    navigation: dict[str, object],
    message_editor: Callable[..., object],
) -> object:
    messages = document.get('messages')
    all_messages = messages if isinstance(messages, list) else []
    chosen = navigation.get('message_index')
    current = chosen if type(chosen) is int and chosen in indexes else None
    items = [
        html.Button(
            [
                html.Strong(_message_title(all_messages[index])),
                html.Small(_active_label(all_messages[index].get('is_active'), feminine=False)),
            ],
            id={'type': MESSAGE_SELECT_TYPE, 'index': index},
            n_clicks=0,
            type='button',
            className=_item_class(current == index),
        )
        for index in indexes
    ]
    details = message_editor(current, all_messages[current]) if current is not None else None
    return _split_editor(items, details, empty='No hay mensajes en esta sección.')


def _split_editor(items: list[object], details: object | None, *, empty: str) -> object:
    is_open = details is not None
    return html.Div(
        [
            html.Div(
                items if items else html.P(empty, className='alarm-family__empty'),
                className='alarm-family__items',
            ),
            html.Div(
                [
                    html.Div(className='alarm-family__modal-backdrop'),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Strong('Editor de configuración'),
                                    html.Button(
                                        'Cerrar',
                                        id=CLOSE_EDITOR_ID,
                                        n_clicks=0,
                                        type='button',
                                        className='btn btn-outline-secondary btn-sm',
                                    ),
                                ],
                                className='alarm-family__modal-header',
                            ),
                            html.Div(details, className='alarm-family__detail'),
                        ],
                        className='alarm-family__modal-dialog',
                        role='dialog',
                        **{'aria-modal': 'true' if is_open else 'false'},
                    ),
                ],
                className='alarm-family__modal',
                hidden=not is_open,
            ),
        ],
        className='alarm-family__workspace',
    )


def _tab_class(selected: bool) -> str:
    return 'alarm-family__tab alarm-family__tab--active' if selected else 'alarm-family__tab'


def _item_class(selected: bool) -> str:
    return 'alarm-family__item alarm-family__item--active' if selected else 'alarm-family__item'


def _rule_title(rule: dict[str, object]) -> str:
    return str(rule.get('display_name') or rule.get('rule_name') or 'Regla sin nombre')


def _rule_subtitle(rule: dict[str, object]) -> str:
    kind = value_label(str(rule.get('kind'))) if rule.get('kind') else 'Sin clasificación'
    criticality = str(rule.get('criticality') or 'Sin criticidad')
    status = _active_label(rule.get('is_active'), feminine=True)
    return f'{kind} · {criticality} · {status}'


def _message_title(message: dict[str, object]) -> str:
    return str(message.get('message_key') or 'Mensaje sin clave')


def _active_label(value: object, *, feminine: bool) -> str:
    if value is True:
        return 'Activa' if feminine else 'Activo'
    if value is False:
        return 'Inactiva' if feminine else 'Inactivo'
    return 'Sin definir'
