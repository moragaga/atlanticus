from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.application.generic import __main__ as cli, bootstrap, host
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.extension import AdaApplicationExtension
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.tools.configuration import ToolRenderTopology
from ada.web.tools.persistence import ToolProjectionResolution, ToolProjectionResolutionState
from atlanticus.web.modules import WebModule
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _settings(tmp_path) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'external-starter',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )


def _ready_resolution() -> ToolProjectionResolution:
    structure = ToolStructure(
        tool_key='sample_tool',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='phase', display_name='Phase'),),
            ),
            ToolComponent(
                key='plant',
                display_name='Plant',
                scope=ToolScope.PLANT,
                subcomponents=(
                    ToolSubcomponent(
                        key='plant_phase',
                        display_name='Plant Phase',
                    ),
                ),
            ),
        ),
    )
    timestamp = datetime(2026, 9, 25, tzinfo=UTC)
    projection = ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('test-release'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=SimpleNamespace(
            structure=structure,
            render_topology=ToolRenderTopology(),
        ),
    )
    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.READY,
        projection=projection,
    )


@pytest.mark.parametrize('configured', [False, True])
def test_external_extension_is_resolved_after_tool_projection(
    monkeypatch, tmp_path, configured: bool
) -> None:
    resolution = (
        _ready_resolution()
        if configured
        else ToolProjectionResolution(state=ToolProjectionResolutionState.UNCONFIGURED)
    )
    seen: dict[str, object] = {}
    expected_runtime = object()
    base_definition = create_application_definition()
    base_module_names = tuple(module.name for module in base_definition.modules)
    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', lambda _settings: resolution)
    monkeypatch.setattr(
        bootstrap,
        'create_definition_from_tool_resolution',
        lambda _resolution, **_kwargs: base_definition,
    )

    def create_web_application(definition):
        seen['definition'] = definition
        return expected_runtime

    monkeypatch.setattr(bootstrap, 'create_web_application', create_web_application)

    external_module = WebModule(name='external-feature')

    def extension_factory(binding: OperationalRenderBinding | None) -> AdaApplicationExtension:
        seen['binding'] = binding
        return AdaApplicationExtension(
            modules=(external_module,),
            page_packages=(),
        )

    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        extension_factory=extension_factory,
    )

    assert runtime is expected_runtime
    definition = seen['definition']
    assert tuple(module.name for module in definition.modules[:-1]) == base_module_names
    assert definition.modules[-1] is external_module
    assert definition.page_packages == ()
    if configured:
        assert isinstance(seen['binding'], OperationalRenderBinding)
        assert seen['binding'].component_keys == ('mine', 'plant')
    else:
        assert seen['binding'] is None


def test_external_extension_preserves_generic_pages_by_default(monkeypatch, tmp_path) -> None:
    resolution = ToolProjectionResolution(state=ToolProjectionResolutionState.UNCONFIGURED)
    base_definition = create_application_definition()
    captured = {}
    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', lambda _settings: resolution)
    monkeypatch.setattr(
        bootstrap,
        'create_definition_from_tool_resolution',
        lambda _resolution, **_kwargs: base_definition,
    )
    monkeypatch.setattr(
        bootstrap,
        'create_web_application',
        lambda definition: captured.setdefault('definition', definition) or object(),
    )

    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        extension_factory=lambda _binding: AdaApplicationExtension(
            modules=(WebModule(name='external-feature'),)
        ),
    )

    assert runtime is captured['definition']
    assert captured['definition'].page_packages == base_definition.page_packages


def test_external_extension_factory_must_return_extension(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        bootstrap,
        '_resolve_tool_projection',
        lambda _settings: ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNCONFIGURED
        ),
    )

    with pytest.raises(TypeError, match='extension_factory'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path),
            extension_factory=lambda _binding: object(),
        )


def test_external_runner_reuses_host_bootstrap_without_second_manager_path(
    monkeypatch,
) -> None:
    forwarded = {}
    runtime = object()
    worker = SimpleNamespace(
        application=runtime,
        close=lambda: forwarded.update(closed=True),
    )

    def create_worker_runtime(**kwargs):
        forwarded.update(kwargs)
        return worker

    monkeypatch.setattr(host, 'create_worker_runtime', create_worker_runtime)
    monkeypatch.setattr(
        host,
        'run_web_application',
        lambda application: forwarded.update(run=application),
    )

    def extension_factory(_binding):
        return AdaApplicationExtension()

    assert cli.run_operational_application is host.run_operational_application
    cli.run_operational_application(extension_factory=extension_factory)

    assert forwarded['extension_factory'] is extension_factory
    assert forwarded['production_identity_provider_factory'] is None
    assert forwarded['run'] is runtime
    assert forwarded['closed'] is True
