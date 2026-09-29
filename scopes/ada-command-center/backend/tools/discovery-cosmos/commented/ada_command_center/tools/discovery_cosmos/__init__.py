# API pública del adapter Cosmos para descubrir Tool Projection.
# El Tool Catalog genérico sigue libre de dependencias físicas adicionales.

from ada_command_center.tools.discovery_cosmos.discovery import (
    DiscoveredTool,
    ToolCatalogConnectionStatus,
    ToolCatalogDiscovery,
    ToolCatalogDiscoveryError,
    ToolCatalogDiscoveryIssue,
    ToolCatalogDiscoveryReport,
    ToolConnectionInspection,
)

__all__ = [
    'DiscoveredTool',
    'ToolCatalogConnectionStatus',
    'ToolCatalogDiscovery',
    'ToolCatalogDiscoveryError',
    'ToolCatalogDiscoveryIssue',
    'ToolCatalogDiscoveryReport',
    'ToolConnectionInspection',
]
