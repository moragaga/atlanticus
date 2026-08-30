from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ada.web.time_status.preview import (
    create_preview_definition,
    create_preview_runtime,
    create_preview_scenario_state,
    preview_scenario_options,
)
from ada.web.ui.time_status import TimeStatusSourceCondition


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


def _component_by_id(component, component_id: str):
    return next((item for item in _walk(component) if _props(item).get('id') == component_id), None)


def _state(key: str, *, age_seconds: int = 0):
    now = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)
    return create_preview_scenario_state(
        key,
        now_utc=now,
        started_at_utc=now - timedelta(seconds=age_seconds),
    )


def test_preview_matrix_covers_required_visual_freeze_scenarios() -> None:
    values = {item['value'] for item in preview_scenario_options()}

    assert {
        'pi_only_fresh',
        'pi_dispatch_fresh',
        'pi_dispatch_detail',
        'pi_preventive',
        'pi_hard_stale',
        'split_health',
        'both_hard_stale',
        'pi_data_error',
        'dispatch_data_error',
        'live_aging',
    } == values


def test_pi_only_fresh_keeps_detail_affordance_with_empty_additional_sources() -> None:
    summary, detail = _state('pi_only_fresh')

    assert summary.dispatch is None
    assert summary.has_detail is True
    assert summary.content_stale is False
    assert detail is None


def test_populated_detail_contains_only_additional_sources_and_keeps_health_neutral() -> None:
    summary, detail = _state('pi_dispatch_detail')

    assert detail is not None
    assert tuple(source.key for source in detail.sources) == ('blockgrade',)
    assert detail.sources[0].value == 'Error'
    assert summary.has_detail is True
    assert summary.content_stale is False
    assert summary.data_error_source_keys == ()


def test_preventive_hard_stale_and_data_error_are_visually_distinct_states() -> None:
    preventive, _ = _state('pi_preventive')
    hard_stale, _ = _state('pi_hard_stale')
    data_error, _ = _state('pi_data_error')

    assert preventive.pi.condition is TimeStatusSourceCondition.PREVENTIVE
    assert hard_stale.pi.condition is TimeStatusSourceCondition.HARD_STALE
    assert data_error.pi.condition is TimeStatusSourceCondition.DATA_ERROR
    assert hard_stale.content_stale is True
    assert data_error.content_stale is False


def test_content_stale_requires_all_control_sources_to_be_hard_stale() -> None:
    split, _ = _state('split_health')
    both, _ = _state('both_hard_stale')

    assert split.pi.condition is TimeStatusSourceCondition.HARD_STALE
    assert split.dispatch is not None
    assert split.dispatch.condition is TimeStatusSourceCondition.FRESH
    assert split.content_stale is False
    assert both.content_stale is True


def test_live_aging_uses_preview_only_fast_thresholds_without_changing_product_contract() -> None:
    fresh, _ = _state('live_aging', age_seconds=0)
    partial, _ = _state('live_aging', age_seconds=13)
    stale, _ = _state('live_aging', age_seconds=17)

    assert fresh.pi.condition is TimeStatusSourceCondition.FRESH
    assert fresh.dispatch is not None
    assert fresh.dispatch.condition is TimeStatusSourceCondition.FRESH
    assert partial.pi.condition is TimeStatusSourceCondition.HARD_STALE
    assert partial.dispatch is not None
    assert partial.dispatch.condition is TimeStatusSourceCondition.PREVENTIVE
    assert partial.content_stale is False
    assert stale.content_stale is True


def test_preview_definition_composes_full_header_and_validation_module() -> None:
    definition = create_preview_definition(tool_key='integrated_operations')
    module_names = tuple(module.name for module in definition.modules)

    assert definition.metadata.application_id == 'ada-time-status-preview-integrated_operations'
    assert definition.metadata.version == '0.1.2'
    assert 'ada-time-status' in module_names
    assert module_names[-1] == 'time-status-visual-preview-controls'


@pytest.fixture(scope='module')
def preview_runtime():
    return create_preview_runtime(tool_key='integrated_operations')


def test_preview_runtime_mounts_real_header_time_status_and_controls(preview_runtime) -> None:
    client = preview_runtime.server.test_client()
    response = client.get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'Operaciones Integradas' in payload
    assert 'ts012-time-status-host' in payload
    assert 'TS-012 · Visual Functional Freeze' in payload
    assert 'Transportado' in payload
    assert 'Gestión Mina' in payload
    assert 'Activas' in payload
    assert 'BlockGrade' in payload


def test_preview_interval_rerenders_only_time_status_header_slot(preview_runtime) -> None:
    with preview_runtime.server.test_request_context('/', headers={'Accept': 'text/html'}):
        assert preview_runtime.server.preprocess_request() is None
        layout = preview_runtime.dash.layout()

    host = _component_by_id(layout, 'ts012-time-status-host')
    interval = _component_by_id(layout, 'ts012-time-status-interval')
    store = _component_by_id(layout, 'ts012-time-status-session')

    assert host is not None
    assert _props(host)['data-ada-slot-key'] == 'time_status'
    assert interval is not None
    assert interval.interval == 2000
    assert store is not None
    assert store.storage_type == 'memory'

    outputs = tuple(preview_runtime.dash.callback_map)
    assert any('ts012-time-status-host.children' in output for output in outputs)
    assert all('operational_header.children' not in output for output in outputs)


def test_preview_supports_process_and_integrated_operations_as_distinct_tool_scopes() -> None:
    integrated = create_preview_definition(tool_key='integrated_operations')
    process = create_preview_definition(tool_key='process')

    assert integrated.metadata.application_id != process.metadata.application_id
    assert integrated.metadata.display_name.endswith('Operaciones Integradas')
    assert process.metadata.display_name.endswith('Procesos')


def test_preview_rejects_unknown_tool_scope() -> None:
    with pytest.raises(ValueError, match='Unsupported preview tool_key'):
        create_preview_definition(tool_key='unknown')


def test_preview_has_no_external_infrastructure_dependency() -> None:
    project = Path(__file__).resolve().parents[1]
    pyproject = (project / 'pyproject.toml').read_text(encoding='utf-8').lower()

    for forbidden in ('cosmos', 'azure', 'sharepoint', 'service-bus', 'databricks'):
        assert forbidden not in pyproject


def test_preview_pins_closed_time_status_header_application_contracts() -> None:
    project = Path(__file__).resolve().parents[1]
    pyproject = (project / 'pyproject.toml').read_text(encoding='utf-8')

    assert 'ada-generic-application==0.1.27' in pyproject
    assert 'ada-web-ui-time-status==0.1.9' in pyproject


def test_ts012b_preview_pins_polished_time_status_contract() -> None:
    project = Path(__file__).resolve().parents[1]
    pyproject = (project / 'pyproject.toml').read_text(encoding='utf-8')

    assert 'ada-generic-application==0.1.27' in pyproject
    assert 'ada-web-ui-time-status==0.1.9' in pyproject
