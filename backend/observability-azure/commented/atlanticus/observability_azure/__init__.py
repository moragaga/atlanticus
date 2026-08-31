"""Extensión Azure Monitor acotada para Atlanticus Observability."""

# Expone la API productiva; estos comentarios sólo documentan la intención del contrato.

from atlanticus.observability_azure.bootstrap import (
    AzureLogBackendFactory,
    AzureObservabilityBootstrapError,
    AzureObservabilityExtension,
    build_azure_observability_extension,
)
from atlanticus.observability_azure.configuration import (
    APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE,
    AZURE_OBSERVABILITY_MODE_VARIABLE,
    AZURE_OBSERVABILITY_PROFILE_VARIABLE,
    AzureObservabilityConfigurationError,
    AzureObservabilityMode,
    AzureObservabilityProfile,
    AzureObservabilitySettings,
)
from atlanticus.observability_azure.exporter import (
    AzureLogBackend,
    AzureMonitorEventSink,
    OpenTelemetryLogBackend,
)
from atlanticus.observability_azure.preview import AzurePreviewSink, AzurePreviewWriter
from atlanticus.observability_azure.projection import AzureProblemEventProjection
from atlanticus.observability_azure.runtime import (
    AzureObservabilityRuntime,
    build_azure_export_runtime,
    build_azure_observability_runtime,
)
from atlanticus.observability_azure.tracing import (
    AzureMonitorTraceBridge,
    AzurePreviewTraceBridge,
)

__version__ = '1.0.0'

__all__ = [
    'APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE',
    'AZURE_OBSERVABILITY_MODE_VARIABLE',
    'AZURE_OBSERVABILITY_PROFILE_VARIABLE',
    'AzureLogBackend',
    'AzureLogBackendFactory',
    'AzureMonitorEventSink',
    'AzureMonitorTraceBridge',
    'AzureObservabilityBootstrapError',
    'AzureObservabilityConfigurationError',
    'AzureObservabilityExtension',
    'AzureObservabilityMode',
    'AzureObservabilityProfile',
    'AzureObservabilityRuntime',
    'AzureObservabilitySettings',
    'AzurePreviewSink',
    'AzureProblemEventProjection',
    'AzurePreviewTraceBridge',
    'AzurePreviewWriter',
    'OpenTelemetryLogBackend',
    '__version__',
    'build_azure_export_runtime',
    'build_azure_observability_extension',
    'build_azure_observability_runtime',
]
