# Punto de entrada público del adaptador Azure para eventos Web.
from atlanticus.web.observability_azure.adapter import (
    WebAzureBackendFactory,
    WebAzureEventSink,
    create_web_azure_event_sink,
)

__all__ = ['WebAzureBackendFactory', 'WebAzureEventSink', 'create_web_azure_event_sink']
