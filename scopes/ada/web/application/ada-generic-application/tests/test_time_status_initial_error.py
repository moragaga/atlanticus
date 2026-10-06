from __future__ import annotations

import json

from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.ui.content_state import ContentStatePresentationMode


def _source_configuration(*, with_dispatch: bool = True):
    source_keys = ['pi']
    control_sources = [SourceControlPolicy('pi', 200, 300)]
    if with_dispatch:
        source_keys.append('dispatch')
        control_sources.append(SourceControlPolicy('dispatch', 400, 600))
    return (
        ToolSourceConsumption(tool_key='process', source_keys=tuple(source_keys)),
        ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=tuple(control_sources),
        ),
    )


def test_tool_source_contract_mounts_time_status_without_runtime_data() -> None:
    consumption, participation = _source_configuration()

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    summary = definition.layout.keywords['time_status_summary']
    module_names = tuple(module.name for module in definition.modules)

    assert summary is not None
    assert summary.pi.condition.value == 'data_error'
    assert summary.dispatch is not None
    assert summary.dispatch.condition.value == 'data_error'
    assert 'ada-time-status' in module_names
    assert 'ada-content-state' in module_names


def test_operational_layout_publishes_tool_and_normal_presentation_context(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration()

    runtime = create_application_runtime(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    payload = json.dumps(
        runtime.server.test_client().get('/_dash-layout').get_json(),
        ensure_ascii=False,
    )

    assert 'data-ada-operational-tool-key' in payload
    assert 'process' in payload
    assert 'data-ada-content-state-presentation' in payload
    assert 'normal' in payload
    assert 'data_error' in payload


def test_authoring_presentation_is_published_without_changing_time_status_state(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration(with_dispatch=False)

    runtime = create_application_runtime(
        source_consumption=consumption,
        source_operational_participation=participation,
        content_state_presentation_mode=ContentStatePresentationMode.AUTHORING,
    )
    payload = json.dumps(
        runtime.server.test_client().get('/_dash-layout').get_json(),
        ensure_ascii=False,
    )

    assert 'authoring' in payload
    assert 'data_error' in payload
