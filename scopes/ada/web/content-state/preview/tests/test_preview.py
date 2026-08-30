from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from ada.web.content_state.core import ContentState
from ada.web.content_state.preview import (
    create_preview_definition,
    create_preview_runtime,
    create_preview_scenario_state,
    create_preview_snapshot,
    preview_scenario_options,
)


def test_preview_exposes_expected_visual_scenarios() -> None:
    options = preview_scenario_options()

    assert len(options) == 8
    assert options[0]['value'] == 'both_fresh'
    assert options[-1]['value'] == 'live_aging'


@pytest.mark.parametrize(
    ('scenario_key', 'pi_condition', 'dispatch_condition'),
    (
        ('both_fresh', 'fresh', 'fresh'),
        ('pi_preventive', 'preventive', 'fresh'),
        ('pi_hard_stale', 'hard_stale', 'fresh'),
        ('dispatch_hard_stale', 'fresh', 'hard_stale'),
        ('pi_data_error', 'data_error', 'fresh'),
        ('mixed_source_error', 'hard_stale', 'data_error'),
        ('both_hard_stale', 'hard_stale', 'hard_stale'),
    ),
)
def test_preview_static_scenarios_build_expected_source_conditions(
    scenario_key: str,
    pi_condition: str,
    dispatch_condition: str,
) -> None:
    now = datetime(2026, 8, 30, 16, 0, tzinfo=UTC)

    summary, detail = create_preview_scenario_state(
        scenario_key,
        now_utc=now,
        started_at_utc=now,
    )

    assert summary.pi.condition.value == pi_condition
    assert summary.dispatch is not None
    assert summary.dispatch.condition.value == dispatch_condition
    assert detail.sources[0].key == 'blockgrade'
    assert detail.sources[0].value == 'Error'


def test_preview_live_aging_crosses_pi_hard_stale_before_dispatch() -> None:
    started_at = datetime(2026, 8, 30, 16, 0, tzinfo=UTC)

    summary, _ = create_preview_scenario_state(
        'live_aging',
        now_utc=started_at + timedelta(seconds=13),
        started_at_utc=started_at,
    )

    assert summary.pi.condition.value == 'hard_stale'
    assert summary.dispatch is not None
    assert summary.dispatch.condition.value == 'preventive'


def test_preview_snapshot_covers_all_header_kpi_keys() -> None:
    snapshot = create_preview_snapshot()
    keys = {definition.kpi_key for definition in snapshot.definitions}

    assert len(snapshot.definitions) == 15
    assert 'preview_transported_shift_actual' in keys
    assert 'preview_recovery_latest' in keys
    assert 'preview_mine_movement_latest' in keys


def test_preview_definition_binds_global_indicators_to_pi_and_dispatch() -> None:
    definition = create_preview_definition()
    preview_keywords = definition.layout.keywords
    base_layout = preview_keywords['base_layout']
    application_keywords = base_layout.keywords

    assert definition.metadata.version == '0.1.0'
    assert application_keywords['global_indicators_runtime_state'] is ContentState.READY
    assert application_keywords['global_indicators_source_keys'] == ('pi', 'dispatch')
    assert preview_keywords['tool_key'] == 'integrated_operations'


def test_preview_definition_keeps_process_tool_isolated() -> None:
    definition = create_preview_definition(tool_key='process')

    assert definition.layout.keywords['tool_key'] == 'process'
    assert definition.metadata.application_id == 'ada-content-state-preview-process'


def test_preview_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match='Unsupported preview tool_key'):
        create_preview_definition(tool_key='other')


def test_preview_rejects_unknown_scenario() -> None:
    now = datetime(2026, 8, 30, 16, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match='Unknown Content State preview scenario'):
        create_preview_scenario_state('other', now_utc=now, started_at_utc=now)


def test_preview_runtime_mounts_real_runtime_wrapper_and_construction_reference(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_preview_runtime()
    client = runtime.server.test_client()
    response = client.get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'CS-008 · Content State Visual Freeze' in payload
    assert 'data-ada-content-state-runtime' in payload
    assert 'global_indicators' in payload
    assert 'pi,dispatch' in payload
    assert 'data-kpi-inspection-key' in payload
    assert client.get('/api/inspection/kpis/preview_transported_shift_actual').status_code == 200
    assert 'preview_reference_component' in payload
    assert 'construction' in payload
    assert 'En construcción' in payload
    assert 'cs008-time-status-host' in payload


def test_preview_callback_rerenders_time_status_without_targeting_global_indicator_wrapper(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_preview_runtime()
    callbacks = tuple(runtime.dash.callback_map)

    assert any('cs008-time-status-host.children' in callback for callback in callbacks)
    assert all('data-ada-content-state' not in callback for callback in callbacks)
    assert all('global_indicators' not in callback for callback in callbacks)
