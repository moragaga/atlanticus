from __future__ import annotations

import json
import tomllib
from importlib.resources import files
from pathlib import Path

from dash import Dash, html
from flask import Flask, Response, jsonify

from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import (
    KpiDefinition,
    KpiDefinitionSnapshot,
    KpiDefinitionSnapshotStore,
)
from ada.web.inspection.surface import (
    build_kpi_inspection_surface_fragment,
    create_kpi_inspection_surface_module,
)
from ada.web.ui.global_indicator import (
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    build_global_indicator,
)
from atlanticus.web.index import IndexPageDefinition, render_index_string
from atlanticus.web.services import ServiceRegistry

_KPI_KEY = 'transported_total'


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


def _snapshot(*definitions: KpiDefinition) -> KpiDefinitionSnapshot:
    return KpiDefinitionSnapshot(definitions=definitions)


def _definition(**fields: str | None) -> KpiDefinition:
    return KpiDefinition(kpi_key=_KPI_KEY, fields=fields)


def _register_api(server: Flask, store: KpiDefinitionSnapshotStore) -> None:
    module = create_kpi_inspection_api_module(store)
    services = ServiceRegistry()
    services.freeze()
    assert module.register_routes is not None
    module.register_routes(server, services)


def _indicator():
    return build_global_indicator(
        state=GlobalIndicatorState(
            key='transportado_card',
            kpi_key=_KPI_KEY,
            label='Transportado',
            unit='kt',
            measurements=(
                GlobalIndicatorMeasurementState(
                    key='turno',
                    label='Turno',
                    actual_value='198',
                    plan_value='220',
                ),
                GlobalIndicatorMeasurementState(
                    key='dia',
                    label='Día',
                    actual_value='201',
                    plan_value='220',
                ),
            ),
        )
    )


def _build_app(store: KpiDefinitionSnapshotStore) -> Dash:
    server = Flask(__name__)
    _register_api(server, store)
    app = Dash(__name__, server=server)
    app.layout = html.Div([_indicator()])

    surface = create_kpi_inspection_surface_module()
    app.index_string = render_index_string(
        application_id='ki010b-empty-definition-flow',
        display_name='KI-010B Empty Definition Flow',
        version='0.1.0',
        definition=IndexPageDefinition(),
        module_contributions=((surface.name, surface.index),),
    )
    return app


def _javascript() -> str:
    return (
        files('ada.web.inspection.surface')
        .joinpath('resources', 'js', '10-kpi-inspection-surface.js')
        .read_text(encoding='utf-8')
    )


def test_same_kpi_transitions_from_missing_to_empty_stub_to_populated_definition() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot())
    app = _build_app(store)
    client = app.server.test_client()

    missing = client.get(f'/api/inspection/kpis/{_KPI_KEY}')
    store.replace(_snapshot(_definition()))
    empty = client.get(f'/api/inspection/kpis/{_KPI_KEY}')
    store.replace(
        _snapshot(
            _definition(
                description='Total material transported during the reporting period.',
                owner='Operations',
                source=None,
            )
        )
    )
    populated = client.get(f'/api/inspection/kpis/{_KPI_KEY}')

    assert missing.status_code == 200
    assert missing.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': _KPI_KEY,
    }
    assert empty.get_json() == {
        'available': True,
        'definition': {},
        'kpi_key': _KPI_KEY,
    }
    assert populated.get_json() == {
        'available': True,
        'definition': {
            'description': 'Total material transported during the reporting period.',
            'owner': 'Operations',
            'source': None,
        },
        'kpi_key': _KPI_KEY,
    }
    assert all(
        response.headers['Cache-Control'] == 'no-store' for response in (missing, empty, populated)
    )


def test_surface_exposes_distinct_missing_empty_ready_and_error_views() -> None:
    markup = build_kpi_inspection_surface_fragment()

    assert 'data-kpi-inspection-view="unavailable"' in markup
    assert 'No hay información descriptiva disponible para este KPI.' in markup
    assert 'data-kpi-inspection-view="ready"' in markup
    assert 'data-kpi-inspection-empty' in markup
    assert 'La definición existe y todavía no contiene información descriptiva.' in markup
    assert 'data-kpi-inspection-fields' in markup
    assert 'data-kpi-inspection-view="error"' in markup
    assert 'Unable to load KPI information.' in markup


def test_controller_maps_missing_to_unavailable_but_empty_stub_to_ready_empty() -> None:
    javascript = _javascript()

    assert (
        "if (!payload.available) {\n        setState('unavailable');\n        return;\n      }"
        in javascript
    )
    assert 'renderDefinition(payload.definition);' in javascript
    assert "setState('ready');" in javascript
    assert 'const entries = Object.entries(definition);' in javascript
    assert 'controller.emptyNode.hidden = entries.length !== 0;' in javascript


def test_controller_maps_non_ok_api_response_to_error_without_fallback_fetch() -> None:
    javascript = _javascript()

    assert 'if (!response.ok)' in javascript
    assert 'Inspection request failed with status' in javascript
    assert "setState('error')" in javascript
    assert "cache: 'no-store'" in javascript
    assert 'XMLHttpRequest' not in javascript
    assert 'axios' not in javascript


def test_global_indicator_and_stable_surface_are_composed_for_the_same_kpi_key() -> None:
    app = _build_app(KpiDefinitionSnapshotStore(_snapshot()))
    client = app.server.test_client()

    page = client.get('/')
    layout = client.get('/_dash-layout')
    payload = json.dumps(layout.get_json(), ensure_ascii=False)
    html_text = page.get_data(as_text=True)

    assert page.status_code == 200
    assert layout.status_code == 200
    assert f'"data-kpi-inspection-key": "{_KPI_KEY}"' in payload
    assert 'id="ada-kpi-inspection-surface"' in html_text
    assert 'atlanticus-runtime-config' in html_text
    assert app.index_string.index('{%app_entry%}') < app.index_string.index(
        'id="ada-kpi-inspection-surface"'
    )


def test_surface_is_stable_and_new_global_indicator_render_keeps_opt_in_identity() -> None:
    first_component = _indicator()
    second_component = _indicator()
    first = first_component.to_plotly_json()['props']
    second = second_component.to_plotly_json()['props']
    javascript = _javascript()

    assert 'data-kpi-inspection-key' not in first
    assert 'data-kpi-inspection-key' not in second
    assert (
        sum(
            1
            for item in _walk(first_component)
            if _props(item).get('data-kpi-inspection-key') == _KPI_KEY
        )
        == 2
    )
    assert (
        sum(
            1
            for item in _walk(second_component)
            if _props(item).get('data-kpi-inspection-key') == _KPI_KEY
        )
        == 2
    )
    assert "document.addEventListener('click', handleClick)" in javascript
    assert '.closest?.(TRIGGER_SELECTOR)' in javascript
    assert 'MutationObserver' not in javascript
    assert 'focusTarget && focusTarget.isConnected' in javascript


def test_surface_can_be_configured_against_a_failing_api_path_for_error_smoke() -> None:
    server = Flask(__name__)

    def fail(_kpi_key: str) -> Response:
        response = jsonify({'error': 'Inspection backend unavailable'})
        response.status_code = 503
        response.headers['Cache-Control'] = 'no-store'
        return response

    server.add_url_rule('/api/inspection-failure/<path:_kpi_key>', view_func=fail, methods=['GET'])
    app = Dash(__name__, server=server)
    app.layout = html.Div([_indicator()])
    surface = create_kpi_inspection_surface_module(api_base_path='/api/inspection-failure')
    app.index_string = render_index_string(
        application_id='ki010b-error-flow',
        display_name='KI-010B Error Flow',
        version='0.1.0',
        definition=IndexPageDefinition(),
        module_contributions=((surface.name, surface.index),),
    )

    response = app.server.test_client().get(f'/api/inspection-failure/{_KPI_KEY}')
    page = app.server.test_client().get('/').get_data(as_text=True)

    assert response.status_code == 503
    assert response.headers['Cache-Control'] == 'no-store'
    assert '/api/inspection-failure' in page
    assert "setState('error')" in _javascript()


def test_empty_definition_flow_adds_no_external_infrastructure_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    dependencies = tuple(project['project']['dependencies'])
    production_files = tuple((root / 'src').rglob('*.py'))

    assert len(production_files) == 1
    assert production_files[0].name == '__init__.py'
    assert not any('azure' in dependency.lower() for dependency in dependencies)
    assert not any('cosmos' in dependency.lower() for dependency in dependencies)
    assert not any('sharepoint' in dependency.lower() for dependency in dependencies)
    assert not any('service-bus' in dependency.lower() for dependency in dependencies)
    assert not any('kpi-configuration' in dependency.lower() for dependency in dependencies)
