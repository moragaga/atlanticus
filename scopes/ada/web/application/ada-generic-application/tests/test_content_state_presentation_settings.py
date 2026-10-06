import pytest
from pydantic import ValidationError

from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.ui.content_state import ContentStatePresentationMode


def test_content_state_presentation_defaults_to_normal() -> None:
    settings = AdaGenericSettings.from_mapping({'ADA_TOOL_NAMESPACE': 'process'})

    assert settings.content_state_presentation_mode is ContentStatePresentationMode.NORMAL


def test_local_authoring_presentation_is_explicitly_supported() -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'process',
            'ADA_CONTENT_STATE_PRESENTATION_MODE': 'authoring',
        }
    )

    assert settings.content_state_presentation_mode is ContentStatePresentationMode.AUTHORING


def test_production_rejects_authoring_presentation() -> None:
    with pytest.raises(
        ValidationError, match='authoring presentation is unavailable in production'
    ):
        AdaGenericSettings.from_mapping(
            {
                'ATLANTICUS_ENVIRONMENT': 'production',
                'ADA_TOOL_NAMESPACE': 'process',
                'ADA_CONTENT_STATE_PRESENTATION_MODE': 'authoring',
            }
        )


def test_operational_bootstrap_threads_authoring_setting_into_definition(monkeypatch) -> None:
    from ada.web.application.generic import bootstrap
    from ada.web.tools.persistence import ToolProjectionResolution, ToolProjectionResolutionState

    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'process',
            'ADA_CONTENT_STATE_PRESENTATION_MODE': 'authoring',
        }
    )
    captured: dict[str, object] = {}
    definition = object()
    runtime = object()

    monkeypatch.setattr(
        bootstrap,
        '_resolve_tool_projection',
        lambda _settings: ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNCONFIGURED
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        'create_definition_from_tool_resolution',
        lambda _resolution, **kwargs: captured.update(kwargs) or definition,
    )
    monkeypatch.setattr(bootstrap, 'create_web_application', lambda value: runtime)

    resolved = bootstrap.create_operational_application_runtime(settings=settings)

    assert resolved is runtime
    assert captured['content_state_presentation_mode'] is ContentStatePresentationMode.AUTHORING
