from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from dash import html
from dash.development.base_component import Component

ALARM_LIVE_BOARD_ID = 'ada-alarm-live-board'


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
    subcomponent_keys: tuple[str, ...]
    grouped: bool = False


def resolve_live_alarm_cards(
    data: object, *, tool_key: str, now: datetime | None = None,
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
                totals = group.get('total_by_area')
                total = sum(v for v in totals.values() if type(v) is int) if isinstance(totals, Mapping) else 0
                results.append(LiveAlarmCard(
                    occurrence_id=f'group:{slot}', slot=slot, color='NEUTRAL',
                    criticality='', category='', title='Distribuidas', cause=f'{total} por área',
                    elapsed='', component_keys=(), subcomponent_keys=(), grouped=True,
                ))
            continue
        source = alarms.get(occurrence_id)
        if not isinstance(source, Mapping):
            continue
        target = source.get('visual_target')
        components, subcomponents = _target_keys(target, tool_key=tool_key)
        color = source.get('color')
        results.append(LiveAlarmCard(
            occurrence_id=occurrence_id,
            slot=slot,
            color=color if color in ('RED', 'YELLOW') else 'NEUTRAL',
            criticality=_label(source.get('criticality')),
            category=' · '.join(x for x in (
                _label(source.get('kind')), _label(source.get('business_category')),
            ) if x),
            title=_label(source.get('title')) or _label(source.get('display_name')) or occurrence_id,
            cause=_label(source.get('cause_text')),
            elapsed=_elapsed(source.get('started_at'), instant),
            component_keys=components,
            subcomponent_keys=subcomponents,
        ))
    return capacity, tuple(results)


def build_live_alarm_cards(data: object, *, tool_key: str) -> tuple[Component, ...]:
    capacity, cards = resolve_live_alarm_cards(data, tool_key=tool_key)
    return tuple(
        html.Article(
            [
                html.Div(
                    [
                        html.Span(card.criticality, className='ada-alarm-live-card__criticality'),
                        html.Span(card.category, className='ada-alarm-live-card__category'),
                        html.Span(card.title, className='ada-alarm-live-card__title', title=card.title),
                    ],
                    className='ada-alarm-live-card__header',
                ),
                html.Div(card.cause, className='ada-alarm-live-card__cause'),
                html.Div(card.elapsed, className='ada-alarm-live-card__elapsed'),
            ],
            className=(
                'ada-alarm-live-card '
                f'ada-alarm-live-card--{card.color.lower()}'
            ),
            style={
                'gridColumn': str(card.slot),
                '--ada-alarm-live-slot-count': str(capacity),
            },
            title=card.title,
            **{
                'data-ada-alarm-occurrence-id': card.occurrence_id,
                'data-ada-alarm-color': card.color,
                'data-ada-alarm-target-components': ' '.join(card.component_keys),
                'data-ada-alarm-target-subcomponents': ' '.join(card.subcomponent_keys),
                'data-ada-alarm-grouped': str(card.grouped).lower(),
                **({} if card.grouped else {
                    'role': 'button',
                    'tabIndex': 0,
                    'aria-label': f'Seleccionar alarma: {card.title}',
                    'aria-pressed': 'false',
                }),
            },
        )
        for card in cards
    )


def resolve_live_alarm_capacity(data: object, *, tool_key: str) -> int:
    return resolve_live_alarm_cards(data, tool_key=tool_key)[0]


def _target_keys(value: object, *, tool_key: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, Mapping) or value.get('tool_key') != tool_key:
        return (), ()
    components = value.get('component_keys')
    subcomponents = value.get('subcomponents')
    component_keys = (
        tuple(dict.fromkeys(x for x in components if isinstance(x, str) and x))
        if isinstance(components, (list, tuple)) else ()
    )
    subcomponent_keys = (
        tuple(dict.fromkeys(
            x['subcomponent_key']
            for x in subcomponents
            if isinstance(x, Mapping)
            and isinstance(x.get('subcomponent_key'), str)
            and x.get('owner_component_key') in component_keys
        ))
        if isinstance(subcomponents, (list, tuple)) else ()
    )
    return component_keys, subcomponent_keys


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
