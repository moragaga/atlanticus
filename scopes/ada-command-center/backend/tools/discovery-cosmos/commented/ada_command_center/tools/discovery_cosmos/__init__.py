from ada_command_center.tools.discovery_cosmos.connections import (
    TOOL_COSMOS_PREFIX,
    ToolCosmosConnectionConfigurationError,
    ToolCosmosConnectionDeclaration,
    ToolCosmosConnectionDeclarations,
    open_tool_catalog_discovery,
)
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
    'TOOL_COSMOS_PREFIX',
    'ToolCosmosConnectionConfigurationError',
    'ToolCosmosConnectionDeclaration',
    'ToolCosmosConnectionDeclarations',
    'open_tool_catalog_discovery',
    'DiscoveredTool',
    'ToolCatalogConnectionStatus',
    'ToolCatalogDiscovery',
    'ToolCatalogDiscoveryError',
    'ToolCatalogDiscoveryIssue',
    'ToolCatalogDiscoveryReport',
    'ToolConnectionInspection',
]
