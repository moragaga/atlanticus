from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

from dash import Dash, Input, Output, dcc, html

from ada.web.inspection.surface import create_kpi_inspection_surface_module
from ada.web.ui.global_indicator import (
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    build_global_indicator,
)
from atlanticus.web.index import IndexPageDefinition, render_index_string

_INTERVAL_ID = 'ki010-interval'
_HOST_ID = 'ki010-global-indicator-host'
_KPI_KEY = 'transported_total'
_INDICATOR_KEY = 'transportado_card'


def _state(tick: int) -> GlobalIndicatorState:
    return GlobalIndicatorState(
        key=_INDICATOR_KEY,
        kpi_key=_KPI_KEY,
        label='Transportado',
        unit='kt',
        measurements=(
            GlobalIndicatorMeasurementState(
                key='turno',
                label='Turno',
                actual_value=str(198 + tick),
                plan_value='220',
            ),
            GlobalIndicatorMeasurementState(
                key='dia',
                label='Día',
                actual_value=str(201 + tick),
                plan_value='220',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState(str(202 + tick)),
    )


def _indicator_for_tick(tick: int):
    return build_global_indicator(state=_state(tick))


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, 'to_plotly_json'):
            yield from _walk(child)


def _actual_values(component) -> tuple[str, ...]:
    values: list[str] = []
    for item in _walk(component):
        props = _props(item)
        classes = props.get('className') or ''
        if 'global-indicator__value--actual' not in classes:
            continue
        children = getattr(item, 'children', ())
        if isinstance(children, (list, tuple)) and children:
            values.append(str(children[0]))
    return tuple(values)


def _build_interval_app() -> tuple[Dash, object]:
    app = Dash(__name__)
    app.layout = html.Div(
        [
            dcc.Interval(id=_INTERVAL_ID, interval=250, n_intervals=0),
            html.Div(_indicator_for_tick(0), id=_HOST_ID),
        ]
    )

    @app.callback(Output(_HOST_ID, 'children'), Input(_INTERVAL_ID, 'n_intervals'))
    def refresh_indicator(n_intervals: int | None):
        return _indicator_for_tick(int(n_intervals or 0))

    return app, refresh_indicator


def test_harness_uses_real_dash_interval_and_replaces_only_indicator_host_children() -> None:
    app, _refresh = _build_interval_app()
    layout_children = app.layout.children
    interval = layout_children[0]
    host = layout_children[1]

    assert interval.__class__.__name__ == 'Interval'
    assert interval.id == _INTERVAL_ID
    assert interval.interval == 250
    assert host.id == _HOST_ID
    assert any(f'{_HOST_ID}.children' in output for output in app.callback_map)


def test_interval_rerenders_replace_indicator_values_without_changing_inspection_identity() -> None:
    _app, refresh = _build_interval_app()
    renders = [refresh(tick) for tick in range(4)]

    assert len({id(component) for component in renders}) == 4
    assert [_props(component)['data-indicator-key'] for component in renders] == [
        _INDICATOR_KEY
    ] * 4
    assert all('data-kpi-inspection-key' not in _props(component) for component in renders)
    assert [
        len(
            [
                item
                for item in _walk(component)
                if _props(item).get('data-kpi-inspection-key') == _KPI_KEY
            ]
        )
        for component in renders
    ] == [3, 3, 3, 3]
    assert [_actual_values(component) for component in renders] == [
        ('198', '201'),
        ('199', '202'),
        ('200', '203'),
        ('201', '204'),
    ]


def test_interval_callback_cannot_replace_stable_inspection_surface() -> None:
    app, _refresh = _build_interval_app()
    callback_outputs = tuple(app.callback_map)

    assert callback_outputs
    assert all('ada-kpi-inspection-surface' not in output for output in callback_outputs)
    assert all('ada-kpi-inspection-key' not in output for output in callback_outputs)


def test_inspection_surface_remains_outside_dash_app_entry_during_host_rerenders() -> None:
    module = create_kpi_inspection_surface_module()
    index = render_index_string(
        application_id='ki010-harness',
        display_name='KI-010 Harness',
        version='0.1.0',
        definition=IndexPageDefinition(),
        module_contributions=((module.name, module.index),),
    )

    app_entry = index.index('{%app_entry%}')
    surface = index.index('id="ada-kpi-inspection-surface"')
    runtime_config = index.index('atlanticus-runtime-config')

    assert app_entry < surface < runtime_config


def test_document_event_delegation_accepts_triggers_created_after_interval_rerender() -> None:
    javascript = (
        files('ada.web.inspection.surface')
        .joinpath('resources', 'js', '10-kpi-inspection-surface.js')
        .read_text(encoding='utf-8')
    )

    assert "const TRIGGER_SELECTOR = '[data-kpi-inspection-key]'" in javascript
    assert "document.addEventListener('click', handleClick)" in javascript
    assert "document.addEventListener('keydown', handleKeydown)" in javascript
    assert '.closest?.(TRIGGER_SELECTOR)' in javascript
    assert 'querySelectorAll(TRIGGER_SELECTOR)' not in javascript
    assert 'MutationObserver' not in javascript


def test_closing_after_interval_replacement_ignores_disconnected_previous_trigger() -> None:
    javascript = (
        files('ada.web.inspection.surface')
        .joinpath('resources', 'js', '10-kpi-inspection-surface.js')
        .read_text(encoding='utf-8')
    )

    assert 'controller.previousFocus = trigger || document.activeElement;' in javascript
    assert 'focusTarget && focusTarget.isConnected' in javascript
    assert "controller.root.dataset.open = 'false';" in javascript


def test_resilience_harness_adds_no_runtime_or_external_infrastructure_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    dependencies = tuple(project['project']['dependencies'])
    production_files = tuple((root / 'src').rglob('*.py'))

    assert len(production_files) == 1
    assert production_files[0].name == '__init__.py'
    assert not any('azure' in dependency.lower() for dependency in dependencies)
    assert not any('cosmos' in dependency.lower() for dependency in dependencies)
    assert not any('selenium' in dependency.lower() for dependency in dependencies)
    assert not any('playwright' in dependency.lower() for dependency in dependencies)
