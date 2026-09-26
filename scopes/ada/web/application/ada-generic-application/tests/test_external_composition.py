from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from dash import html

from ada.web.application.generic import bootstrap
from ada.web.application.generic.composition import AdaApplicationComposition
from ada.web.application.generic.layout import build_body_application_layout
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.persistence import ToolProjectionResolution, ToolProjectionResolutionState
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _settings(tmp_path) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'external-starter',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )


def _ready_resolution() -> ToolProjectionResolution:
    structure = ToolStructure(
        tool_key='sample-tool',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='phase', display_name='Phase'),),
            ),
        ),
    )
    timestamp = datetime(2026, 9, 25, tzinfo=UTC)
    projection = ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('test-release'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=SimpleNamespace(structure=structure),
    )
    return ToolProjectionResolution(state=ToolProjectionResolutionState.READY, projection=projection)


@pytest.mark.parametrize('configured', [False, True])
def test_external_composition_is_resolved_after_tool_projection(
    monkeypatch, tmp_path, configured: bool
) -> None:
    resolution = (
        _ready_resolution()
        if configured
        else ToolProjectionResolution(state=ToolProjectionResolutionState.UNCONFIGURED)
    )
    seen: dict[str, object] = {}
    expected_runtime = object()
    expected_definition = object()
    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', lambda _settings: resolution)

    def create_definition(_resolution, **kwargs):
        assert _resolution is resolution
        seen['definition_kwargs'] = kwargs
        return expected_definition

    monkeypatch.setattr(bootstrap, 'create_definition_from_tool_resolution', create_definition)
    monkeypatch.setattr(
        bootstrap, 'create_web_application',
        lambda definition: expected_runtime if definition is expected_definition else None,
    )

    def composition_factory(binding: OperationalRenderBinding | None) -> AdaApplicationComposition:
        seen['binding'] = binding
        return AdaApplicationComposition(
            modules=(),
            layout=build_body_application_layout,
            operational_body_factory=lambda _binding: html.Div(id='external-operational-body'),
        )

    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path), composition_factory=composition_factory
    )
    assert runtime is expected_runtime
    kwargs = seen['definition_kwargs']
    assert isinstance(kwargs['composition'], AdaApplicationComposition)
    if configured:
        assert isinstance(seen['binding'], OperationalRenderBinding)
        assert seen['binding'].component_keys == ('mine',)
        assert kwargs['operational_render_binding'] is seen['binding']
    else:
        assert seen['binding'] is None
        assert kwargs['operational_render_binding'] is None


def test_external_composition_can_remain_page_based_without_renderers(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', lambda _settings: _ready_resolution())
    captured = {}
    expected_runtime = object()
    monkeypatch.setattr(
        bootstrap,
        'create_definition_from_tool_resolution',
        lambda _resolution, **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(bootstrap, 'create_web_application', lambda _definition: expected_runtime)
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        composition_factory=lambda _binding: AdaApplicationComposition(
            modules=(), layout=build_body_application_layout
        ),
    )
    assert runtime is expected_runtime
    assert captured['operational_render_binding'] is None


def test_external_runner_reuses_cli_bootstrap_without_second_manager_path(monkeypatch) -> None:
    from ada.web.application.generic import __main__ as cli
    from ada.web.application.generic import host

    forwarded = {}
    runtime = object()
    monkeypatch.setattr(
        cli, 'AdaGenericSettings',
        lambda: SimpleNamespace(environment=SimpleNamespace(is_local=True)),
    )
    monkeypatch.setattr(
        cli, 'ManagerStartupOptions', lambda: SimpleNamespace(provider='disabled'),
    )
    monkeypatch.setattr(
        cli, 'create_operational_application_runtime',
        lambda **kwargs: forwarded.update(kwargs) or runtime,
    )
    monkeypatch.setattr(cli, 'run_web_application', lambda value: forwarded.update(run=value))
    composition_factory = lambda _binding: None

    assert host.run_operational_application is cli.run_operational_application
    host.run_operational_application(composition_factory=composition_factory)

    assert forwarded['composition_factory'] is composition_factory
    assert forwarded['run'] is runtime
