from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from dash import html
from dash.development.base_component import Component

from .module import ADA_ALARM_LIVE_SURFACE_ASSET_LAYER

ALARM_LIVE_BOARD_ID = 'ada-alarm-live-board'
_KIND_LABELS = {'RISK': 'Riesgo', 'IMPACT': 'Impacto'}
_BUSINESS_CATEGORY_LABELS = {
    'ECOLOGY': 'Medio Ambiente',
    'PRODUCTIVITY': 'Productividad',
    'SAFETY': 'Seguridad y Salud',
    'SAFETY_HEALTH': 'Seguridad y Salud',
    'COSTS': 'Costos',
}
_BUSINESS_CATEGORY_ICONS = {
    'ECOLOGY': 'ecology',
    'PRODUCTIVITY': 'productivity',
    'SAFETY': 'safety',
    'SAFETY_HEALTH': 'safety',
    'COSTS': 'costs',
}
_ICON_FILENAMES = {
    'ecology': 'medio-ambiente',
    'productivity': 'productividad',
    'safety': 'seguridad-salud',
    'costs': 'costos',
}


@dataclass(frozen=True, slots=True)
class LiveAlarmCard:
    occurrence_id: str
    slot: int
    color: str
    criticality: str
    category: str
    title: str
    cause: str
    elapsed: str
    component_keys: tuple[str, ...]
    subcomponent_addresses: tuple[tuple[str, str], ...]
    grouped: bool = False
    area: str = ''
    group_members: tuple[LiveAlarmCard, ...] = ()
    display_component_key: str = ''
    display_scope: str = ''
    category_icon: str = ''


def resolve_live_alarm_cards(
    data: object,
    *,
    tool_key: str,
    now: datetime | None = None,
) -> tuple[int, tuple[LiveAlarmCard, ...]]:
    if not isinstance(tool_key, str) or not tool_key.strip():
        raise ValueError('Alarm surface tool key is required')
    if not isinstance(data, Mapping) or data.get('tool_key') != tool_key:
        return 1, ()
    document = data.get('live')
    if not isinstance(document, Mapping) or document.get('tool_key') != tool_key:
        return 1, ()
    if document.get('schema_version') != 2 or document.get('retired') is True:
        return 1, ()
    capacity = document.get('max_visible_slots')
    if type(capacity) is not int or capacity < 1:
        return 1, ()
    alarms = document.get('alarms')
    view = document.get('operator_view')
    if not isinstance(alarms, Mapping) or not isinstance(view, list):
        return capacity, ()
    instant = now or datetime.now(timezone.utc)
    results: list[LiveAlarmCard] = []
    for item in sorted(
        (x for x in view if isinstance(x, Mapping)),
        key=lambda x: x.get('slot') if type(x.get('slot')) is int else 0,
    ):
        slot = item.get('slot')
        if type(slot) is not int or not 1 <= slot <= capacity:
            continue
        occurrence_id = item.get('occurrence_id')
        if not isinstance(occurrence_id, str):
            group = item.get('group')
            if isinstance(group, Mapping) and group.get('kind') == 'DISTRIBUTED':
                visible = group.get('visible_by_area')
                totals = group.get('total_by_area')
                members: list[LiveAlarmCard] = []
                descriptions: list[str] = []
                if isinstance(visible, Mapping) and isinstance(totals, Mapping):
                    for area, occurrence_ids in visible.items():
                        if not isinstance(area, str) or not isinstance(occurrence_ids, list):
                            continue
                        total = totals.get(area)
                        if type(total) is int:
                            descriptions.append(
                                f'{_area_label(area)} {len(occurrence_ids)}/{total}'
                            )
                        for member_id in occurrence_ids:
                            member = _resolve_card(
                                alarms,
                                member_id,
                                slot=slot,
                                tool_key=tool_key,
                                instant=instant,
                                area=area,
                            )
                            if member is not None:
                                members.append(member)
                results.append(
                    LiveAlarmCard(
                        occurrence_id=f'group:{slot}',
                        slot=slot,
                        color='NEUTRAL',
                        criticality='',
                        category='',
                        title='Distribuidas',
                        cause=' · '.join(descriptions),
                        elapsed='',
                        component_keys=(),
                        subcomponent_addresses=(),
                        grouped=True,
                        group_members=tuple(members),
                    )
                )
            continue
        card = _resolve_card(
            alarms,
            occurrence_id,
            slot=slot,
            tool_key=tool_key,
            instant=instant,
        )
        if card is not None:
            results.append(card)
    return capacity, tuple(results)


def build_live_alarm_cards(
    data: object, *, tool_key: str, component_keys: tuple[str, ...] = (),
) -> tuple[Component, ...]:
    capacity, cards = resolve_live_alarm_cards(data, tool_key=tool_key)
    return tuple(
        _build_group(card, capacity=capacity)
        if card.grouped
        else _build_card(card, capacity=capacity, component_keys=component_keys)
        for card in cards
    )


def _build_group(group: LiveAlarmCard, *, capacity: int) -> Component:
    members = group.group_members
    if not members:
        return _build_card(group, capacity=capacity)
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(group.title),
                    html.Span(group.cause),
                ],
                className='ada-alarm-live-group__header',
            ),
            html.Div(
                [
                    _build_card(member, capacity=capacity, carousel_index=index)
                    for index, member in enumerate(members)
                ],
                className='ada-alarm-live-group__slides',
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        type='button',
                        className='ada-alarm-live-group__previous',
                        **{
                            'aria-label': 'Alarma anterior del grupo',
                            'data-ada-alarm-group-navigation': 'previous',
                        },
                    ),
                    html.Span(
                        f'1/{len(members)}',
                        className='ada-alarm-live-group__counter',
                        **{'aria-live': 'polite'},
                    ),
                    html.Button(
                        '›',
                        type='button',
                        className='ada-alarm-live-group__next',
                        **{
                            'aria-label': 'Alarma siguiente del grupo',
                            'data-ada-alarm-group-navigation': 'next',
                        },
                    ),
                ]
                if len(members) > 1
                else [],
                className='ada-alarm-live-group__navigation',
            ),
        ],
        className='ada-alarm-live-group',
        style={'gridColumn': str(group.slot)},
        **{
            'data-ada-alarm-group-slot': str(group.slot),
            'data-ada-alarm-group-kind': 'DISTRIBUTED',
            'aria-label': 'Alarmas distribuidas',
            'role': 'group',
        },
    )


def _build_card(
    card: LiveAlarmCard,
    *,
    capacity: int,
    carousel_index: int | None = None,
    component_keys: tuple[str, ...] = (),
) -> Component:
    grouped = carousel_index is not None
    icon = None
    if card.category_icon:
        icon = html.Img(
            src=(
                f'/assets/{ADA_ALARM_LIVE_SURFACE_ASSET_LAYER.target_name}/img/alarms/'
                f'{_ICON_FILENAMES[card.category_icon]}.svg'
            ),
            alt='',
            className=(
                f'ada-alarm-live-card__icon ada-alarm-live-card__icon--{card.category_icon}'
            ),
            **{'aria-hidden': 'true'},
        )
    criticality = None
    if card.criticality:
        criticality = html.Span(card.criticality, className='ada-alarm-live-card__criticality')
    column = (
        component_keys.index(card.display_component_key) + 1
        if card.display_component_key and card.display_component_key in component_keys
        else card.slot
    )
    return html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            icon,
                            html.Span(card.category, className='ada-alarm-live-card__category'),
                        ],
                        className='ada-alarm-live-card__header-content',
                    ),
                    criticality,
                ],
                className='ada-alarm-live-card__header',
            ),
            html.Div(
                [
                    html.Span(_area_label(card.area), className='ada-alarm-live-card__area')
                    if grouped
                    else None,
                    html.Div(card.title, className='ada-alarm-live-card__title', title=card.title),
                    html.Div(card.cause, className='ada-alarm-live-card__cause'),
                ],
                className='ada-alarm-live-card__body',
            ),
            html.Div(
                [
                    html.Span(card.elapsed, className='ada-alarm-live-card__elapsed'),
                    html.Div(
                        [
                            html.Button(
                                'Información',
                                type='button',
                                disabled=True,
                                className=(
                                    'ada-alarm-live-card__action '
                                    'ada-alarm-live-card__action--information'
                                ),
                            ),
                            html.Button(
                                'Gestionar',
                                type='button',
                                disabled=True,
                                className=(
                                    'ada-alarm-live-card__action '
                                    'ada-alarm-live-card__action--manage'
                                ),
                            ),
                        ],
                        className='ada-alarm-live-card__actions',
                    ),
                ],
                className='ada-alarm-live-card__footer',
            ),
        ],
        className=f'ada-alarm-live-card ada-alarm-live-card--{card.color.lower()}',
        style={}
        if grouped
        else {
            'gridColumn': str(column),
            '--ada-alarm-live-slot-count': str(capacity),
        },
        hidden=bool(grouped and carousel_index != 0),
        title=card.title,
        **{
            'data-ada-alarm-occurrence-id': card.occurrence_id,
            'data-ada-alarm-slot': str(card.slot),
            'data-ada-alarm-color': card.color,
            'data-ada-alarm-target-components': ' '.join(card.component_keys),
            'data-ada-alarm-target-addresses': json.dumps(
                card.subcomponent_addresses, separators=(',', ':'),
            ),
            'data-ada-alarm-display-component-key': card.display_component_key,
            'data-ada-alarm-display-scope': card.display_scope,
            'data-ada-alarm-grouped': str(card.grouped).lower(),
            **(
                {}
                if not grouped
                else {
                    'data-ada-alarm-group-item': 'true',
                    'data-ada-alarm-group-area': card.area,
                }
            ),
            **(
                {}
                if card.grouped
                else {
                    'role': 'button',
                    'tabIndex': 0,
                    'aria-label': f'Seleccionar alarma: {card.title}',
                    'aria-pressed': 'false',
                }
            ),
        },
    )


def _resolve_card(
    alarms: Mapping,
    occurrence_id: object,
    *,
    slot: int,
    tool_key: str,
    instant: datetime,
    area: str = '',
) -> LiveAlarmCard | None:
    if not isinstance(occurrence_id, str):
        return None
    source = alarms.get(occurrence_id)
    if not isinstance(source, Mapping):
        return None
    target = source.get('visual_target')
    components, subcomponents = _target_keys(target, tool_key=tool_key)
    display_component = ''
    display_scope = ''
    if isinstance(target, Mapping) and target.get('tool_key') == tool_key:
        if target.get('tool_kind') == 'integrated_operations':
            candidate = target.get('display_component_key')
            scope = target.get('display_scope')
            if (
                isinstance(candidate, str)
                and candidate in components
                and scope in ('mine', 'plant')
            ):
                display_component = candidate
                display_scope = scope
    color = source.get('color')
    kind = _label(source.get('kind'))
    business_category = _label(source.get('business_category'))
    normalized_category = business_category.upper()
    category = ' · '.join(
        part
        for part in (
            _KIND_LABELS.get(kind.upper(), kind),
            _BUSINESS_CATEGORY_LABELS.get(normalized_category, business_category),
        )
        if part
    )
    return LiveAlarmCard(
        occurrence_id=occurrence_id,
        slot=slot,
        color=color if color in ('RED', 'YELLOW') else 'NEUTRAL',
        criticality=_label(source.get('criticality')),
        category=category,
        category_icon=_BUSINESS_CATEGORY_ICONS.get(normalized_category, ''),
        title=_label(source.get('title')) or _label(source.get('display_name')) or occurrence_id,
        cause=_label(source.get('cause_text')),
        elapsed=_elapsed(source.get('started_at'), instant),
        component_keys=components,
        subcomponent_addresses=subcomponents,
        area=area,
        display_component_key=display_component,
        display_scope=display_scope,
    )


def _area_label(area: str) -> str:
    return {'MINE': 'Mina', 'PLANT': 'Planta'}.get(area, area)


def resolve_live_alarm_capacity(data: object, *, tool_key: str) -> int:
    return resolve_live_alarm_cards(data, tool_key=tool_key)[0]


def _target_keys(
    value: object, *, tool_key: str,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    if not isinstance(value, Mapping) or value.get('tool_key') != tool_key:
        return (), ()
    components = value.get('component_keys')
    subcomponents = value.get('subcomponents')
    component_keys = (
        tuple(dict.fromkeys(x for x in components if isinstance(x, str) and x))
        if isinstance(components, (list, tuple))
        else ()
    )
    subcomponent_addresses = (
        tuple(
            dict.fromkeys(
                (x['owner_component_key'], x['subcomponent_key'])
                for x in subcomponents
                if isinstance(x, Mapping)
                and isinstance(x.get('subcomponent_key'), str)
                and x['subcomponent_key']
                and isinstance(x.get('owner_component_key'), str)
                and x['owner_component_key']
            )
        )
        if isinstance(subcomponents, (list, tuple))
        else ()
    )
    return component_keys, subcomponent_addresses


def _label(value: object) -> str:
    return value if isinstance(value, str) else ''


def _elapsed(value: object, instant: datetime) -> str:
    if not isinstance(value, str):
        return ''
    try:
        started = datetime.fromisoformat(value.replace('Z', '+00:00'))
        seconds = int((instant - started).total_seconds())
    except (ValueError, TypeError):
        return ''
    if started.utcoffset() is None or seconds < 0:
        return ''
    if seconds < 60:
        return f'{seconds} s'
    if seconds < 3600:
        return f'{seconds // 60} min'
    if seconds < 86400:
        return f'{seconds // 3600} h'
    return f'{seconds // 86400} d'
