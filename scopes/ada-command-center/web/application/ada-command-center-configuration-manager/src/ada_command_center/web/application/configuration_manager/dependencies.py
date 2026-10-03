from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada.contracts.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from ada_command_center.web.tools.discovery_cosmos.manager import ToolCatalogManagerService
from atlanticus.web.manager import ManagerEntry, ManagerModule, ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.recovery import ToolUsersRecoveryService
from atlanticus.web.users.store import UsersRuntimeStore


@dataclass(frozen=True, slots=True)
class CommandCenterAdministrationDependencies:
    profiles_module: ManagerModule
    navigation_module: ManagerModule
    users_entry: ManagerEntry
    profiles_projection_store: ProjectionStore[ProfileCatalog]
    navigation_projection_store: ProjectionStore[NavigationConfigurationCatalog]
    users_runtime_store: UsersRuntimeStore
    users_projection_entry: ManagerEntry | None = None
    users_recovery: ToolUsersRecoveryService | Callable[[], ToolUsersRecoveryService] | None = None
    users_snapshot_ids: Callable[[], tuple[str, ...]] | None = None


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    source_store: SourceStore
    projection_store: ProjectionStore[AlarmConfigurationSnapshot]
    principal_provider: ManagerPrincipalProvider
    tool_reference_reader: AlarmToolReferenceReader | None = None
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    tool_catalog_manager: ToolCatalogManagerService | None = None
    administration: CommandCenterAdministrationDependencies | None = None
