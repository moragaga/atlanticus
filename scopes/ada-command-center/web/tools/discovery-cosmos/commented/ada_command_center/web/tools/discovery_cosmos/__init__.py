# API publica del descubridor. Exponemos servicios sin duplicar responsabilidades.
from ada_command_center.web.tools.discovery_cosmos.connections import (
    TOOL_COSMOS_PREFIX,
    ToolCosmosConnectionConfigurationError,
    ToolCosmosConnectionDeclaration,
    ToolCosmosConnectionDeclarations,
    open_tool_catalog_discovery,
)
from ada_command_center.web.tools.discovery_cosmos.discovery import (
    DiscoveredTool,
    ToolCatalogConnectionStatus,
    ToolCatalogDiscovery,
    ToolCatalogDiscoveryError,
    ToolCatalogDiscoveryIssue,
    ToolCatalogDiscoveryReport,
    ToolConnectionInspection,
)
from ada_command_center.web.tools.discovery_cosmos.manager import (
    AdoptedToolCatalog,
    ToolCandidateSummary,
    ToolCatalogManagerConflictError,
    ToolCatalogManagerService,
    ToolCatalogReview,
    ToolConnectionSummary,
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
    'AdoptedToolCatalog',
    'ToolCandidateSummary',
    'ToolCatalogManagerConflictError',
    'ToolCatalogManagerService',
    'ToolCatalogReview',
    'ToolConnectionSummary',
]
