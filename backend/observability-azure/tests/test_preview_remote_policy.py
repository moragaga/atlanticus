from pathlib import Path

from atlanticus.kernel import DataSanitizer
from atlanticus.observability import (
    EventAudience,
    EventCategory,
    EventSeverity,
    ObservabilityEvent,
    ObservabilitySettings,
)
from atlanticus.observability_azure import (
    AzureObservabilityMode,
    build_azure_observability_extension,
)


def _settings(tmp_path: Path) -> ObservabilitySettings:
    return ObservabilitySettings.build(
        application='ada',
        service='dispatch-job',
        module='dispatch',
        environment='dev',
        volume_path=tmp_path,
    )


def test_preview_preserves_informational_operational_contract(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    extension = build_azure_observability_extension(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
        },
        volume_path=tmp_path,
    )

    assert extension.settings.mode is AzureObservabilityMode.PREVIEW
    extension.sink.emit(
        ObservabilityEvent(
            name='runtime.execution.summary',
            category=EventCategory.LIFECYCLE,
            audience=EventAudience.OPERATIONS,
            severity=EventSeverity.INFO,
        ),
        settings,
        DataSanitizer(),
    )

    assert tuple(tmp_path.rglob('azure-preview.jsonl'))
