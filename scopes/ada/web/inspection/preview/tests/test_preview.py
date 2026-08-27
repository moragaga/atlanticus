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


def test_preview_covers_populated_empty_and_missing_kpi_definitions() -> None:
    snapshot = create_preview_snapshot()
    definitions = {definition.kpi_key: definition for definition in snapshot.definitions}

    assert set(definitions) == {'transported_total', 'recovery'}
    assert dict(definitions['transported_total'].fields) == {
        'description': 'Tonelaje total transportado por la operación.',
        'operational_context': 'Indicador piloto con definición descriptiva completa.',
        'owner': 'Operaciones',
        'source': 'Dispatch',
    }
    assert dict(definitions['recovery'].fields) == {}
    assert 'mine_movement' not in definitions


def test_preview_uses_three_real_global_indicator_adopters() -> None:
    collection = create_preview_global_indicators()

    assert [indicator.kpi_key for indicator in collection.indicators] == [
        'transported_total',
        'recovery',
        'mine_movement',
    ]
    assert all(len(indicator.measurements) == 2 for indicator in collection.indicators)
    assert all(indicator.last_measurement is not None for indicator in collection.indicators)


def test_preview_extends_generic_application_only_with_inspection_api_and_surface() -> None:
    definition = create_preview_definition()
    module_names = [module.name for module in definition.modules]

    assert definition.metadata.application_id == 'ada-kpi-inspection-preview'
    assert definition.metadata.version == '0.1.1'
    assert module_names[-2:] == ['kpi-inspection-api', 'kpi-inspection-surface']
    assert module_names.count('kpi-inspection-api') == 1
    assert module_names.count('kpi-inspection-surface') == 1


@pytest.fixture(scope='module')
def preview_runtime():
    return create_preview_runtime()


def test_preview_runtime_serves_all_three_inspection_states(preview_runtime) -> None:
    client = preview_runtime.server.test_client()

    populated = client.get('/api/inspection/kpis/transported_total')
    empty = client.get('/api/inspection/kpis/recovery')
    missing = client.get('/api/inspection/kpis/mine_movement')

    assert populated.status_code == 200
    assert populated.get_json()['available'] is True
    assert populated.get_json()['definition']['owner'] == 'Operaciones'
    assert empty.status_code == 200
    assert empty.get_json() == {
        'kpi_key': 'recovery',
        'available': True,
        'definition': {},
    }
    assert missing.status_code == 200
    assert missing.get_json() == {
        'kpi_key': 'mine_movement',
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


def test_preview_uses_value_only_inspection_triggers() -> None:
    for state in create_preview_global_indicators().indicators:
        component = build_global_indicator(state=state)
        assert 'data-kpi-inspection-key' not in _props(component)
        triggers = [
            item
            for item in _walk(component)
            if _props(item).get('data-kpi-inspection-key') == state.kpi_key
        ]
        assert len(triggers) == 3
        assert all(_props(item)['role'] == 'button' for item in triggers)


def test_preview_surface_is_dark_square_selectable_and_loading_locked() -> None:
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
