# Presentación específica de Alarm Configuration siguiendo los tokens de Atlanticus.
from __future__ import annotations

from collections.abc import Callable

from dash import html

from ada_command_center.web.alarms.configuration.web.families import (
    FamilySummary,
    family_catalog,
    selected_family,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    FAMILY_SELECT_TYPE,
    FAMILY_TAB_TYPE,
    MESSAGE_SELECT_TYPE,
    RULE_SELECT_TYPE,
)


# La UI recibe editores del contrato existente sin replicar campos del dominio.
def build_family_panel(
    document: dict[str, object],
    references: dict[str, object] | None,
    navigation: dict[str, object] | None,
    *,
    rule_editor: Callable[..., object],
    message_editor: Callable[..., object],
) -> object:
    catalog = family_catalog(document)
    current = navigation if isinstance(navigation, dict) else {}
    if current.get('page') == 'global':
        return _global_messages(catalog.global_message_indexes, document, current, message_editor)
    key = selected_family(current, document)
    if key is None:
        return _family_listing(catalog.families, len(catalog.global_message_indexes))
    family = catalog.get(key)
    if family is None:
        return _family_listing(catalog.families, len(catalog.global_message_indexes))
    return _family_content(family, document, references, current, rule_editor, message_editor)


# La portada sólo muestra agrupaciones derivadas del documento actual.
def _family_listing(families: tuple[FamilySummary, ...], global_count: int) -> object:
    cards = [
        html.Button(
            [
                html.Strong(family.key or 'Sin familia'),
                html.Small(
                    f'{len(family.rule_indexes)} reglas · {len(family.message_indexes)} mensajes'
                ),
                html.Span('Abrir familia', className='alarm-family__card-action'),
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
                    html.H4('Familias configuradas'),
                    html.P('Selecciona una familia para administrar sus reglas y mensajes.'),
                ],
                className='alarm-family__heading',
            ),
            html.Div(cards, className='alarm-family__cards')
            if cards
            else html.P('Todavía no existen familias configuradas.'),
            html.P(f'Mensajes globales: {global_count}', className='alarm-family__note'),
        ],
        className='alarm-family__section',
    )


# El detalle separa reglas y mensajes, conservando índices reales para Dash.
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
    if current_tab == 'rules':
        content = _rule_list(family.rule_indexes, document, references, navigation, rule_editor)
    else:
        content = _message_list(family.message_indexes, document, navigation, message_editor)
    return html.Section(
        [
            html.Div(
                [html.H4(family.key or 'Sin familia'), tabs],
                className='alarm-family__heading',
            ),
            content,
        ],
        className='alarm-family__section',
    )


# Los mensajes globales se editan fuera de una familia.
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


# Se monta sólo la regla seleccionada para evitar el formulario interminable.
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
        rule_editor(current, all_rules[current], all_rules, all_messages, references)
        if current is not None
        else html.P('Selecciona una regla para editar su configuración.')
    )
    return _split_editor(items, details, empty='Esta familia todavía no tiene reglas.')


# La lista de mensajes preserva índices para el contrato de callbacks existente.
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
    details = (
        message_editor(current, all_messages[current])
        if current is not None
        else html.P('Selecciona un mensaje para editarlo.')
    )
    return _split_editor(items, details, empty='No hay mensajes en esta sección.')


# El layout usa los tokens visuales compartidos de Atlanticus mediante CSS propio.
def _split_editor(items: list[object], details: object, *, empty: str) -> object:
    return html.Div(
        [
            html.Div(items if items else html.P(empty), className='alarm-family__items'),
            html.Div(details, className='alarm-family__detail'),
        ],
        className='alarm-family__split',
    )


def _tab_class(selected: bool) -> str:
    return 'alarm-family__tab alarm-family__tab--active' if selected else 'alarm-family__tab'


def _item_class(selected: bool) -> str:
    return 'alarm-family__item alarm-family__item--active' if selected else 'alarm-family__item'


def _rule_title(rule: dict[str, object]) -> str:
    return str(rule.get('display_name') or rule.get('rule_name') or 'Regla sin nombre')


def _rule_subtitle(rule: dict[str, object]) -> str:
    kind = str(rule.get('kind') or 'Sin clasificación')
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
