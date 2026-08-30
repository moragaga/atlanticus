from datetime import UTC, datetime

import pytest
from dash import html
from dash.development.base_component import Component

from ada.web.ui.time_status import (
    TimeStatusDefinitionError,
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
    build_time_status,
    build_time_status_summary,
)


def _props(component: Component) -> dict:
    return component.to_plotly_json()['props']


def _walk(component: Component):
    yield component
    children = _props(component).get('children')
    if isinstance(children, Component):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if isinstance(child, Component):
                yield from _walk(child)


def _text_content(component: Component) -> tuple[str, ...]:
    values: list[str] = []
    for item in _walk(component):
        children = _props(item).get('children')
        if isinstance(children, str):
            values.append(children)
        elif isinstance(children, (list, tuple)):
            values.extend(child for child in children if isinstance(child, str))
    return tuple(values)


def _source(
    key: str,
    *,
    condition: TimeStatusSourceCondition,
    warning: int,
    stale: int,
    relative_age: str | None = 'hace más de 20 segundos',
) -> TimeStatusSourceState:
    timestamp = datetime(2026, 8, 28, 22, 0, tzinfo=UTC)
    if condition is TimeStatusSourceCondition.DATA_ERROR:
        timestamp = None
        relative_age = None
    return TimeStatusSourceState(
        key=key,
        label='PI' if key == 'pi' else 'Dispatch',
        policy=TimeStatusFreshnessPolicy(warning, stale),
        condition=condition,
        relative_age_text=relative_age,
        timestamp_utc=timestamp,
    )


def _pi_state(*, has_detail: bool = False) -> TimeStatusSummaryState:
    return TimeStatusSummaryState(
        pi=_source('pi', condition=TimeStatusSourceCondition.FRESH, warning=200, stale=300),
        has_detail=has_detail,
    )


def test_pi_only_summary_exposes_clock_marker_and_policy_metadata() -> None:
    component = build_time_status_summary(state=_pi_state())
    root = _props(component)

    assert root['data-has-dispatch'] == 'false'
    assert root['data-content-stale'] == 'false'
    pi = next(item for item in _walk(component) if _props(item).get('data-source-key') == 'pi')
    pi_props = _props(pi)
    assert pi_props['data-source-condition'] == 'fresh'
    assert pi_props['data-warning-after-seconds'] == '200'
    assert pi_props['data-stale-after-seconds'] == '300'
    assert any(
        _props(item).get('data-ada-time-status-clock') == 'true' for item in _walk(component)
    )


def test_pi_and_dispatch_sources_are_the_only_detail_trigger() -> None:
    component = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi', condition=TimeStatusSourceCondition.PREVENTIVE, warning=200, stale=300
            ),
            dispatch=_source(
                'dispatch',
                condition=TimeStatusSourceCondition.FRESH,
                warning=400,
                stale=600,
            ),
            has_detail=True,
        )
    )
    root = _props(component)
    children = root['children']
    sources = _props(children[0])
    current = _props(children[1])

    assert root['data-has-dispatch'] == 'true'
    assert 'data-ada-time-status-detail-trigger' not in root
    assert sources['data-ada-time-status-detail-trigger'] == 'true'
    assert sources['role'] == 'button'
    assert sources['tabIndex'] == 0
    assert sources['aria-expanded'] == 'false'
    assert sources['aria-label'] == 'Ver fuentes de datos adicionales'
    assert 'data-ada-time-status-detail-trigger' not in current
    assert (
        sum(1 for item in _walk(component) if _props(item).get('data-source-key') is not None) == 2
    )


def test_hard_stale_and_data_error_are_distinct_dom_states() -> None:
    stale = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi',
                condition=TimeStatusSourceCondition.HARD_STALE,
                warning=200,
                stale=300,
            )
        )
    )
    error = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi',
                condition=TimeStatusSourceCondition.DATA_ERROR,
                warning=200,
                stale=300,
            )
        )
    )

    assert _props(stale)['data-content-stale'] == 'true'
    assert _props(stale)['data-has-data-error'] == 'false'
    assert _props(error)['data-content-stale'] == 'false'
    assert _props(error)['data-has-data-error'] == 'true'

    error_source = next(
        item for item in _walk(error) if _props(item).get('data-source-key') == 'pi'
    )
    error_content = _props(_props(error_source)['children'])['children']
    source_icon = next(
        item
        for item in error_content
        if _props(item).get('data-ada-time-status-source-icon') == 'true'
    )
    source_value = next(
        item
        for item in error_content
        if _props(item).get('data-ada-time-status-source-value') == 'true'
    )

    assert 'bi-cloud-slash' in _props(source_icon)['className']
    assert 'bi-exclamation-triangle' in _props(source_value)['className']
    assert _props(source_value)['aria-label'] == 'Error de información temporal'


def test_data_error_keeps_pi_dispatch_detail_trigger_available() -> None:
    component = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi',
                condition=TimeStatusSourceCondition.DATA_ERROR,
                warning=200,
                stale=300,
            ),
            has_detail=True,
        )
    )
    sources = _props(_props(component)['children'][0])

    assert sources['data-ada-time-status-detail-trigger'] == 'true'
    assert sources['role'] == 'button'
    assert sources['aria-expanded'] == 'false'


def test_composed_time_status_anchors_detail_as_summary_sibling() -> None:
    detail = html.Div('Injected detail', **{'data-test-detail': 'true'})
    component = build_time_status(
        tool_key='process', state=_pi_state(has_detail=True), detail=detail
    )
    root = _props(component)
    children = root['children']

    assert root['data-ada-time-status-container'] == 'true'
    assert len(children) == 2
    assert _props(children[0])['data-component-key'] == 'time_status'
    summary_children = _props(children[0])['children']
    assert _props(summary_children[0])['data-ada-time-status-detail-trigger'] == 'true'
    assert 'data-ada-time-status-detail-trigger' not in _props(children[0])
    surface = _props(children[1])
    assert surface['data-ada-time-status-detail-surface'] == 'true'
    assert surface['hidden'] is True
    assert surface['aria-hidden'] == 'true'
    assert surface['children'] is detail


def test_detail_enabled_without_additional_sources_renders_explicit_empty_state() -> None:
    component = build_time_status(tool_key='process', state=_pi_state(has_detail=True))
    root = _props(component)
    surface = _props(root['children'][1])
    empty = next(
        item
        for item in _walk(surface['children'])
        if _props(item).get('data-ada-time-status-detail-empty') == 'true'
    )
    text = _text_content(surface['children'])

    assert surface['data-ada-time-status-detail-surface'] == 'true'
    assert 'Sin fuentes adicionales' in text
    assert 'Esta herramienta no consume fuentes de datos adicionales.' in text
    assert _props(empty)['data-ada-time-status-detail-empty'] == 'true'


def test_composed_time_status_without_detail_has_no_surface_or_trigger() -> None:
    component = build_time_status(tool_key='process', state=_pi_state())
    children = _props(component)['children']

    assert len(children) == 1
    assert _props(children[0])['data-has-detail'] == 'false'
    assert 'data-ada-time-status-detail-trigger' not in _props(children[0])
    assert not any(
        _props(item).get('data-ada-time-status-detail-surface') == 'true'
        for item in _walk(component)
    )


def test_detail_content_requires_detail_enabled_in_summary_contract() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='requires has_detail=True'):
        build_time_status(
            tool_key='process', state=_pi_state(), detail=html.Div('Unexpected detail')
        )


def test_detail_enabled_summary_exposes_keyboard_button_contract_closed_by_default() -> None:
    component = build_time_status(
        tool_key='process', state=_pi_state(has_detail=True), detail=html.Div('Detail')
    )
    root = _props(component)
    summary = _props(root['children'][0])
    sources = _props(summary['children'][0])
    current = _props(summary['children'][1])

    assert root['data-ada-time-status-detail-open'] == 'false'
    assert 'role' not in summary
    assert sources['role'] == 'button'
    assert sources['tabIndex'] == 0
    assert sources['aria-expanded'] == 'false'
    assert 'role' not in current


def test_summary_without_detail_does_not_enter_keyboard_interaction_contract() -> None:
    component = build_time_status(tool_key='process', state=_pi_state())
    root = _props(component)
    summary = _props(root['children'][0])

    assert 'data-ada-time-status-detail-open' not in root
    assert 'role' not in summary
    assert 'tabIndex' not in summary
    assert 'aria-expanded' not in summary


def test_composed_time_status_publishes_stable_tool_key_for_rerender_identity() -> None:
    component = build_time_status(
        tool_key='integrated_operations',
        state=_pi_state(has_detail=True),
        detail=html.Div('Detail'),
    )

    assert _props(component)['data-ada-time-status-tool-key'] == 'integrated_operations'


def test_composed_time_status_rejects_empty_tool_key() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='tool_key must not be empty'):
        build_time_status(tool_key='   ', state=_pi_state())


def _detail_props(component: Component) -> list[dict]:
    return [
        _props(item)
        for item in _walk(component)
        if _props(item).get('data-ada-time-status-detail-source') == 'true'
    ]


def test_dynamic_detail_renders_only_additional_sources_as_informational() -> None:
    from ada.web.ui.time_status import (
        TimeStatusDetailSourceState,
        TimeStatusDetailState,
        build_time_status_detail,
    )

    detail = build_time_status_detail(
        state=TimeStatusDetailState(
            sources=(
                TimeStatusDetailSourceState(
                    key='blockgrade', label='BlockGrade', value='2026-08-29T22:00:00Z'
                ),
                TimeStatusDetailSourceState(
                    key='fabrica', label='Fábrica', value='Sin información temporal disponible'
                ),
            )
        )
    )
    rows = _detail_props(detail)
    text = _text_content(detail)

    assert [row['data-source-key'] for row in rows] == ['blockgrade', 'fabrica']
    assert [row['data-source-role'] for row in rows] == ['informational', 'informational']
    assert 'Fuentes adicionales' in text
    assert 'PI' not in [row['data-source-key'] for row in rows]
    assert 'Dispatch' not in [row['data-source-key'] for row in rows]


def test_informational_error_is_rendered_opaquely_without_affecting_summary_health() -> None:
    from ada.web.ui.time_status import (
        TimeStatusDetailSourceState,
        TimeStatusDetailState,
        build_time_status_detail,
    )

    detail = build_time_status_detail(
        state=TimeStatusDetailState(
            sources=(
                TimeStatusDetailSourceState(key='blockgrade', label='BlockGrade', value='Error'),
            )
        )
    )
    component = build_time_status(
        tool_key='process',
        state=_pi_state(has_detail=True),
        detail=detail,
    )
    root = _props(component)
    summary = _props(root['children'][0])
    blockgrade = next(
        row for row in _detail_props(root['children'][1]) if row['data-source-key'] == 'blockgrade'
    )

    assert summary['data-content-stale'] == 'false'
    assert summary['data-has-data-error'] == 'false'
    assert blockgrade['data-source-role'] == 'informational'
    assert 'data-source-condition' not in blockgrade
    assert _props(blockgrade['children'][1])['children'] == 'Error'


def test_time_status_presentation_avoids_native_title_tooltips() -> None:
    from ada.web.ui.time_status import (
        TimeStatusDetailSourceState,
        TimeStatusDetailState,
        build_time_status_detail,
    )

    detail = build_time_status_detail(
        state=TimeStatusDetailState(
            sources=(
                TimeStatusDetailSourceState(key='blockgrade', label='BlockGrade', value='Error'),
            )
        )
    )
    component = build_time_status(
        tool_key='process',
        state=_pi_state(has_detail=True),
        detail=detail,
    )

    assert all('title' not in _props(item) for item in _walk(component))


def test_summary_source_exposes_stable_client_freshness_markers() -> None:
    component = build_time_status_summary(state=_pi_state())
    source = next(
        item
        for item in _walk(component)
        if _props(item).get('data-ada-time-status-source') == 'true'
    )
    source_props = _props(source)
    content = source_props['children']
    content_props = _props(content)

    assert source_props['data-source-key'] == 'pi'
    assert source_props['data-source-timestamp-utc']
    assert source_props['data-warning-after-seconds'] == '200'
    assert source_props['data-stale-after-seconds'] == '300'
    assert content_props['data-ada-time-status-source-content'] == 'true'
    assert any(
        _props(child).get('data-ada-time-status-source-icon') == 'true'
        for child in content_props['children']
    )
    assert any(
        _props(child).get('data-ada-time-status-source-value') == 'true'
        for child in content_props['children']
    )


def test_detail_surface_publishes_bottom_as_initial_collision_placement() -> None:
    component = build_time_status(
        tool_key='process', state=_pi_state(has_detail=True), detail=html.Div('Detail')
    )
    surface = _props(_props(component)['children'][1])

    assert surface['data-ada-time-status-detail-placement'] == 'bottom'
