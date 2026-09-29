# Tool Catalog es una entrada independiente; Alarm Configuration conserva su propio Manager.
from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.tools.discovery_cosmos.manager import ToolCatalogManagerService
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from atlanticus.web.manager import ManagerPrincipalProvider
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.store import SourceStore


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    source_store: SourceStore
    projection_store: ProjectionStore[AlarmConfigurationSnapshot]
    principal_provider: ManagerPrincipalProvider
    tool_reference_reader: AlarmToolReferenceReader | None = None
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    tool_catalog_manager: ToolCatalogManagerService | None = None
