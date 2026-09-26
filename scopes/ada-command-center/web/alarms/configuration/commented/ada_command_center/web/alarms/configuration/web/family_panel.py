# Presentación específica de Alarm Configuration siguiendo los tokens de Atlanticus.
from __future__ import annotations

from collections.abc import Callable

from dash import html

from ada_command_center.web.alarms.configuration.web.diagnostics import (
    authoring_issues,
    readiness_hints,
)
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
    MODAL_BACK_ID,
    MODAL_SAVE_BUTTON_ID,
    MODAL_SAVE_RESULT_ID,
    RULE_SELECT_TYPE,
)
from ada_command_center.web.alarms.configuration.web.labels import value_label
from ada_command_center.web.alarms.configuration.web.pagination import (
    list_page,
    list_pagination,
)


# La UI recibe editores del contrato existente sin replicar campos del dominio.
# La paginación no altera los índices originales del documento.
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
        return _family_listing(
            catalog.families, len(catalog.global_message_indexes), pending_keys, current
        )
    family = catalog.get(key)
    if family is None:
        return _family_listing(
            catalog.families, len(catalog.global_message_indexes), pending_keys, current
        )
    return _family_content(family, document, references, current, rule_editor, message_editor)


# La portada combina agrupaciones derivadas y familias pendientes en memoria.
def _family_listing(
    families: tuple[FamilySummary, ...],
    global_count: int,
    pending: list[str],
    navigation: dict[str, object],
) -> object:
    page = list_page(families, navigation, 'families')
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
                html.Span('Administrar ›', className='alarm-family__card-action'),
            ],
            id={'type': FAMILY_SELECT_TYPE, 'index': page.request.offset + position},
            n_clicks=0,
            className='alarm-family__card',
            type='button',
        )
        for position, family in enumerate(page.items)
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
            html.Div(
                cards,
                className='alarm-family__cards alarm-page__results',
                **{'data-page-size': str(page.request.page_size)},
            )
            if cards
            else html.P(
                'Todavía no existen familias. Crea una para comenzar.',
                className='alarm-family__empty',
            ),
            list_pagination(page, 'families'),
            html.P(f'Mensajes globales: {global_count}', className='alarm-family__note'),
            html.Div(id=MODAL_SAVE_RESULT_ID, hidden=True),
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
                f'Mensajes de la familia ({len(family.message_indexes)})',
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
                            html.Small('Las identidades de familia son estables.'),
                        ],
                        className='alarm-family__title',
                    ),
                    tabs,
                ],
                className='alarm-family__heading',
            ),
            content,
            html.P(
                'Esta familia está preparada en esta sesión. Agrega una regla o un mensaje '
                'para incorporarla al documento.',
                className='alarm-family__notice',
            )
            if not family.rule_indexes and not family.message_indexes
            else None,
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
            html.Div(
                [
                    html.H4('Mensajes globales'),
                    html.P('Estos mensajes pueden utilizarse desde cualquier familia.'),
                ],
                className='alarm-family__heading',
            ),
            _message_list(indexes, document, navigation, message_editor, listing='global'),
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
    page = list_page(indexes, navigation, 'rules')
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
        for index in page.items
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
    return _split_editor(
        items,
        details,
        empty='Esta familia todavía no tiene reglas.',
        pagination=list_pagination(page, 'rules'),
        page_size=page.request.page_size,
        title='Editar regla',
        validation=_item_issues(document, 'Regla', current),
    )


# La lista de mensajes preserva índices para el contrato de callbacks existente.
def _message_list(
    indexes: tuple[int, ...],
    document: dict[str, object],
    navigation: dict[str, object],
    message_editor: Callable[..., object],
    *,
    listing: str = 'messages',
) -> object:
    messages = document.get('messages')
    all_messages = messages if isinstance(messages, list) else []
    page = list_page(indexes, navigation, listing)
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
        for index in page.items
    ]
    details = message_editor(current, all_messages[current]) if current is not None else None
    return _split_editor(
        items,
        details,
        empty='No hay mensajes en esta sección.',
        pagination=list_pagination(page, listing),
        page_size=page.request.page_size,
        title='Editar mensaje',
        validation=_item_issues(document, 'Mensaje', current),
    )


# El layout usa los tokens visuales compartidos de Atlanticus mediante CSS propio.
def _item_issues(document: dict[str, object], kind: str, index: int | None) -> tuple[str, ...]:
    if index is None:
        return ()
    prefix = f'{kind} {index + 1}'
    issues = tuple(
        issue
        for issue in authoring_issues(document)
        if issue.startswith(prefix + ' ·') or issue.startswith(prefix + ':')
    )
    if kind == 'Regla':
        issues += tuple(
            issue for issue in readiness_hints(document) if issue.startswith(prefix + ' ·')
        )
    return issues


def _split_editor(
    items: list[object],
    details: object | None,
    *,
    empty: str,
    pagination: object,
    title: str,
    validation: tuple[str, ...],
    page_size: int,
) -> object:
    is_open = details is not None
    return html.Div(
        [
            html.Div(
                items if items else html.P(empty, className='alarm-family__empty'),
                className='alarm-family__items alarm-page__results',
                **{'data-page-size': str(page_size)},
            ),
            pagination,
            html.Div(
                [
                    html.Div(className='alarm-family__modal-backdrop'),
                    html.Div(
                        [
                            html.Header(
                                [
                                    html.Div(
                                        [
                                            html.Small('CENTRO DE CONTROL · CONFIGURACIÓN'),
                                            html.H3(title),
                                        ]
                                    ),
                                    html.Button(
                                        'Cerrar',
                                        id=CLOSE_EDITOR_ID,
                                        n_clicks=0,
                                        type='button',
                                        className='btn btn-outline-secondary btn-sm',
                                    ),
                                ],
                                className='alarm-family__modal-header modal-header',
                            ),
                            html.Div(details, className='alarm-family__detail'),
                            html.Footer(
                                [
                                    html.Div(
                                        [
                                            html.Strong('Revisión de este elemento'),
                                            html.Ul([html.Li(issue) for issue in validation])
                                            if validation
                                            else html.Span(
                                                'Sin campos básicos pendientes. '
                                                'El documento completo se valida antes de guardarse.'
                                            ),
                                        ],
                                        className='alarm-family__validation',
                                        role='status',
                                    ),
                                    html.Div(
                                        id=MODAL_SAVE_RESULT_ID,
                                        className='alarm-family__save-result',
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                'Volver',
                                                id=MODAL_BACK_ID,
                                                n_clicks=0,
                                                type='button',
                                                className='btn btn-outline-secondary btn-sm',
                                            ),
                                            html.Button(
                                                'Guardar borrador completo',
                                                id=MODAL_SAVE_BUTTON_ID,
                                                n_clicks=0,
                                                type='button',
                                                className='btn btn-primary btn-sm',
                                            ),
                                        ],
                                        className='alarm-family__modal-actions',
                                    ),
                                ],
                                className='alarm-family__modal-footer modal-footer',
                            ),
                        ],
                        className='alarm-family__modal-dialog modal-content',
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
