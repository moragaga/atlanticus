# Fachada pública headless de Tool Configuration; no importa la capa Dash.
from ada.web.tools.configuration.errors import (
    ToolConfigurationProjectionError,
    ToolConfigurationSourceError,
)
from ada.web.tools.configuration.models import ToolConfiguration
from ada.web.tools.configuration.render_topology import ToolRenderTopology
from ada.web.tools.configuration.operational import (
    validate_ada_operational_tool_configuration,
    validate_ada_operational_tool_sources,
)
from ada.web.tools.configuration.source_projection import (
    ToolProjectionBuilder,
    create_tool_projection_service,
)
from ada.web.tools.configuration.source_release import (
    TOOL_SOURCE_DOCUMENT_TYPE,
    TOOL_SOURCE_RESOURCE_PATH,
    TOOL_SOURCE_SCHEMA_VERSION,
    ToolSourceCodec,
    ToolSourcePayload,
    ToolSourceRelease,
    ToolSourceService,
)
from atlanticus.web.source.models import SourceKey

# Identidad canónica del Source durable de Tool Configuration.
TOOLS_SOURCE_KEY = SourceKey('tools')

__all__ = [
    'TOOLS_SOURCE_KEY',
    'TOOL_SOURCE_DOCUMENT_TYPE',
    'TOOL_SOURCE_RESOURCE_PATH',
    'TOOL_SOURCE_SCHEMA_VERSION',
    'ToolConfiguration',
    'ToolConfigurationProjectionError',
    'ToolConfigurationSourceError',
    'ToolRenderTopology',
    'ToolProjectionBuilder',
    'ToolSourceCodec',
    'ToolSourcePayload',
    'ToolSourceRelease',
    'ToolSourceService',
    'create_tool_projection_service',
    'validate_ada_operational_tool_configuration',
    'validate_ada_operational_tool_sources',
]
