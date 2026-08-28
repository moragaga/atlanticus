from __future__ import annotations

from pathlib import Path

import pytest

from ada.web.inspection.preview import (
    create_preview_definition,
    create_preview_global_indicators,
    create_preview_runtime,
    create_preview_snapshot,
)
from ada.web.ui.global_indicator import build_global_indicator


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


def _inspection_keys(component) -> tuple[str, ...]:
    return tuple(
        _props(item)['data-kpi-inspection-key']
        for item in _walk(component)
        if _props(item).get('data-kpi-inspection-key')
    )


def _component_by_id(component, component_id: str):
    return next(
        (item for item in _walk(component) if _props(item).get('id') == component_id),
        None,
    )


def test_preview_covers_populated_empty_and_missing_per_value_definitions() -> None:
    snapshot = create_preview_snapshot()
    definitions = {definition.kpi_key: definition for definition in snapshot.definitions}

    assert definitions['transported_shift_actual'].fields['window'] == 'Turno'
    assert definitions['transported_shift_plan'].fields['value_type'] == 'Plan'
    assert dict(definitions['recovery_day_plan'].fields) == {}
    assert 'mine_movement_latest' not in definitions


def test_preview_uses_three_real_global_indicators_with_five_independent_value_keys_each() -> None:
    collection = create_preview_global_indicators()

    assert len(collection.indicators) == 3
    for indicator in collection.indicators:
        component = build_global_indicator(state=indicator)
        keys = _inspection_keys(component)
        assert len(keys) == 5
        assert len(set(keys)) == 5
        assert all(key.startswith(f'{indicator.key.removesuffix("_card")}_') for key in keys)


def test_preview_extends_generic_application_with_interval_api_and_surface() -> None:
    definition = create_preview_definition()
    module_names = [module.name for module in definition.modules]

    assert definition.metadata.application_id == 'ada-kpi-inspection-preview'
    assert definition.metadata.version == '0.1.3'
    assert module_names[-3:] == [
        'kpi-inspection-preview-interval',
        'kpi-inspection-api',
        'kpi-inspection-surface',
    ]
    assert module_names.count('kpi-inspection-api') == 1
    assert module_names.count('kpi-inspection-surface') == 1


@pytest.fixture(scope='module')
def preview_runtime():
    return create_preview_runtime()


def test_preview_runtime_serves_populated_empty_and_missing_value_states(preview_runtime) -> None:
    client = preview_runtime.server.test_client()

    populated = client.get('/api/inspection/kpis/transported_shift_actual')
    empty = client.get('/api/inspection/kpis/recovery_day_plan')
    missing = client.get('/api/inspection/kpis/mine_movement_latest')

    assert populated.status_code == 200
    assert populated.get_json()['available'] is True
    assert populated.get_json()['definition']['window'] == 'Turno'
    assert empty.status_code == 200
    assert empty.get_json() == {
        'kpi_key': 'recovery_day_plan',
        'available': True,
        'definition': {},
    }
    assert missing.status_code == 200
    assert missing.get_json() == {
        'kpi_key': 'mine_movement_latest',
        'available': False,
        'definition': None,
    }
    assert all(
        response.headers['Cache-Control'] == 'no-store' for response in (populated, empty, missing)
    )


def test_preview_keeps_inspection_surface_outside_dash_managed_entry(preview_runtime) -> None:
    html = preview_runtime.server.test_client().get('/').get_data(as_text=True)

    app_entry = html.index('react-entry-point')
    surface = html.index('ada-kpi-inspection-surface')
    assert surface > app_entry


def test_preview_interval_changes_values_without_changing_per_value_identity() -> None:
    first = create_preview_global_indicators(tick=0)
    second = create_preview_global_indicators(tick=1)

    assert first.indicators[0].measurements[0].actual_value.value == '184'
    assert second.indicators[0].measurements[0].actual_value.value == '185'
    assert first.indicators[1].measurements[0].actual_value.value == '91.4'
    assert second.indicators[1].measurements[0].actual_value.value == '91.5'

    first_keys = tuple(
        _inspection_keys(build_global_indicator(state=indicator)) for indicator in first.indicators
    )
    second_keys = tuple(
        _inspection_keys(build_global_indicator(state=indicator)) for indicator in second.indicators
    )
    assert second_keys == first_keys


def test_preview_runtime_uses_real_interval_and_replaces_only_global_indicator_children(
    preview_runtime,
) -> None:
    with preview_runtime.server.test_request_context('/', headers={'Accept': 'text/html'}):
        assert preview_runtime.server.preprocess_request() is None
        layout = preview_runtime.dash.layout()

    interval = _component_by_id(layout, 'kiv003-global-indicator-interval')
    host = _component_by_id(layout, 'kiv003-global-indicators-host')

    assert interval is not None
    assert interval.__class__.__name__ == 'Interval'
    assert interval.interval == 2000
    assert host is not None
    assert host.className == 'global-indicators'

    outputs = tuple(preview_runtime.dash.callback_map)
    assert 'kiv003-global-indicators-host.children' in outputs
    assert all('ada-kpi-inspection-surface' not in output for output in outputs)


def test_preview_adds_local_api_delay_only_to_make_loading_lock_observable() -> None:
    project = Path(__file__).resolve().parents[1]
    runtime = (project / 'src' / 'ada' / 'web' / 'inspection' / 'preview' / 'runtime.py').read_text(
        encoding='utf-8'
    )

    assert '_PREVIEW_API_DELAY_SECONDS = 0.75' in runtime
    assert 'class _PreviewDelayedSnapshotStore(KpiDefinitionSnapshotStore)' in runtime
    assert 'sleep(_PREVIEW_API_DELAY_SECONDS)' in runtime


def test_preview_has_no_external_infrastructure_dependency() -> None:
    project = Path(__file__).resolve().parents[1]
    text = (project / 'pyproject.toml').read_text(encoding='utf-8').lower()

    for forbidden in ('cosmos', 'azure', 'sharepoint', 'service-bus', 'databricks'):
        assert forbidden not in text


def test_preview_test_environment_does_not_shadow_installed_atlanticus_packages() -> None:
    project = Path(__file__).resolve().parents[1]
    pyproject = (project / 'pyproject.toml').read_text(encoding='utf-8')

    pythonpath_block = pyproject.split('pythonpath = [', 1)[1].split(']', 1)[0]

    assert 'web/framework/observability/src' not in pythonpath_block
    assert 'web/capabilities/navigation/core/src' not in pythonpath_block
    assert '../../application/ada-generic-application/src' not in pythonpath_block


def test_preview_values_are_the_only_inspection_triggers() -> None:
    for state in create_preview_global_indicators().indicators:
        component = build_global_indicator(state=state)
        assert 'data-kpi-inspection-key' not in _props(component)
        triggers = [
            item for item in _walk(component) if _props(item).get('data-kpi-inspection-key')
        ]
        trigger_classes = [_props(item).get('className', '') for item in triggers]

        assert len(triggers) == 5
        assert sum('global-indicator__value--actual' in value for value in trigger_classes) == 2
        assert sum('global-indicator__value--plan' in value for value in trigger_classes) == 2
        assert (
            sum('global-indicator__last-measurement-value' in value for value in trigger_classes)
            == 1
        )
        assert all(_props(item)['role'] == 'button' for item in triggers)


def test_preview_surface_keeps_dark_square_loading_lock_and_pointer_focus_policy() -> None:
    project = Path(__file__).resolve().parents[2] / 'surface'
    css = (
        project
        / 'src'
        / 'ada'
        / 'web'
        / 'inspection'
        / 'surface'
        / 'resources'
        / 'css'
        / '10-kpi-inspection-surface.css'
    ).read_text(encoding='utf-8')
    javascript = (
        project
        / 'src'
        / 'ada'
        / 'web'
        / 'inspection'
        / 'surface'
        / 'resources'
        / 'js'
        / '10-kpi-inspection-surface.js'
    ).read_text(encoding='utf-8')

    assert 'var(--dark-color, #313131)' in css
    assert 'border-radius: 0;' in css
    assert 'user-select: text;' in css
    assert 'function setBusy(isBusy)' in javascript
    assert 'if (controller.request) {\n      return;\n    }' in javascript
    assert "controller.restoreFocusOnClose = activationMode === 'keyboard';" in javascript
    assert "inspectTrigger(trigger, 'pointer')" in javascript
    assert "inspectTrigger(trigger, 'keyboard')" in javascript
