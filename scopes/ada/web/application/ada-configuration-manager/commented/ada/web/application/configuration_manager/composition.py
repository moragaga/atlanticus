# Espejo pedagógico: ADA compone la capability Users ya construida y no adopta ownership de su lifecycle.
from __future__ import annotations

from collections.abc import Callable

from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.kpi_definitions import (
    KpiDefinitionManagerWebContext,
    build_kpi_definition_history_preview,
    build_kpi_definition_manager_configuration,
    create_kpi_definition_manager_web_module,
)
from ada.web.application.configuration_manager.kpis import (
    KpiManagerWebContext,
    build_kpi_history_preview,
    build_kpi_manager_configuration,
    create_kpi_manager_web_module,
)
from ada.web.application.configuration_manager.tools import (
    ToolManagerWebContext,
    build_tool_history_preview,
    build_tool_manager_configuration,
    create_tool_manager_web_module,
)
from ada.web.application.configuration_manager.workflows import (
    KpiConfigurationManagerDraftValidationWorkflow,
    KpiConfigurationManagerSourceWorkflow,
    KpiDefinitionManagerDraftValidationWorkflow,
    KpiDefinitionManagerSourceWorkflow,
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
    ToolManagerDraftValidationWorkflow,
    ToolManagerSourceWorkflow,
)
from ada.web.application.configuration_manager.workspace import ManagerWorkspaceBridge
from atlanticus.web.bootstrap import create_bootstrap_web_module
from atlanticus.web.manager import (
    ManagerModule,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_result_id,
    workflow_saved_draft_id,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.configuration.web import (
    NavigationAdminWebContext,
    build_navigation_admin_configuration,
    build_navigation_history_preview,
    create_navigation_admin_web_module,
)
from atlanticus.web.services import ServiceRegistry

MANAGER_ROUTE_PREFIX = '/manager'

USERS_MANAGER_ACCESS_KEY = 'users.manage'
PROFILES_MANAGER_ACCESS_KEY = 'profiles.manage'
NAVIGATION_MANAGER_ACCESS_KEY = 'navigation.manage'
TOOLS_MANAGER_ACCESS_KEY = 'tools.manage'
KPI_MANAGER_ACCESS_KEY = 'kpis.manage'

NAVIGATION_SOURCE_SERVICE = 'ada.configuration-manager.navigation.source'
NAVIGATION_SOURCE_READER_SERVICE = 'ada.configuration-manager.navigation.source-reader'
NAVIGATION_SOURCE_HISTORY_SERVICE = 'ada.configuration-manager.navigation.source-history'
NAVIGATION_PROJECTION_SERVICE = 'ada.configuration-manager.navigation.projection'
NAVIGATION_DRAFT_VALIDATION_SERVICE = 'ada.configuration-manager.navigation.validation'

TOOLS_SOURCE_SERVICE = 'ada.configuration-manager.tools.source'
TOOLS_SOURCE_READER_SERVICE = 'ada.configuration-manager.tools.source-reader'
TOOLS_SOURCE_HISTORY_SERVICE = 'ada.configuration-manager.tools.source-history'
TOOLS_PROJECTION_SERVICE = 'ada.configuration-manager.tools.projection'
TOOLS_DRAFT_VALIDATION_SERVICE = 'ada.configuration-manager.tools.validation'

KPI_SOURCE_SERVICE = 'ada.configuration-manager.kpis.source'
KPI_SOURCE_READER_SERVICE = 'ada.configuration-manager.kpis.source-reader'
KPI_SOURCE_HISTORY_SERVICE = 'ada.configuration-manager.kpis.source-history'
KPI_PROJECTION_SERVICE = 'ada.configuration-manager.kpis.projection'
KPI_DRAFT_VALIDATION_SERVICE = 'ada.configuration-manager.kpis.validation'

KPI_DEFINITION_SOURCE_SERVICE = 'ada.configuration-manager.kpi-definitions.source'
KPI_DEFINITION_SOURCE_READER_SERVICE = 'ada.configuration-manager.kpi-definitions.source-reader'
KPI_DEFINITION_SOURCE_HISTORY_SERVICE = 'ada.configuration-manager.kpi-definitions.source-history'
KPI_DEFINITION_PROJECTION_SERVICE = 'ada.configuration-manager.kpi-definitions.projection'
KPI_DEFINITION_DRAFT_VALIDATION_SERVICE = 'ada.configuration-manager.kpi-definitions.validation'


def build_configuration_manager_surface(
    dependencies: ConfigurationManagerDependencies,
) -> ManagerSurfaceDefinition:
    def actor_provider() -> str:
        return dependencies.principal_provider().subject_id

    navigation_workspace = ManagerWorkspaceBridge(
        owner_subject_id_provider=actor_provider,
        source_snapshot_provider=dependencies.navigation_source.get_current,
    )
    tools_workspace = ManagerWorkspaceBridge(
        owner_subject_id_provider=actor_provider,
        source_snapshot_provider=dependencies.tools_source.get_current,
    )
    navigation_context = NavigationAdminWebContext(
        workspace_payload_reader=navigation_workspace.read_payload,
        workspace_payload_writer=navigation_workspace.write_payload,
        draft_store_id=workflow_draft_id('navigation'),
        saved_draft_store_id=workflow_saved_draft_id('navigation'),
        draft_save_action_id=workflow_action_id('navigation', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('navigation'),
        can_manage=lambda: _has_access(
            dependencies.principal_provider(),
            NAVIGATION_MANAGER_ACCESS_KEY,
        ),
        source_name=dependencies.navigation_source_name,
        projection_name=dependencies.navigation_projection_name,
    )
    tools_context = ToolManagerWebContext(
        workspace_payload_reader=tools_workspace.read_payload,
        workspace_payload_writer=tools_workspace.write_payload,
        draft_store_id=workflow_draft_id('tools'),
        saved_draft_store_id=workflow_saved_draft_id('tools'),
        draft_save_action_id=workflow_action_id('tools', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('tools'),
        result_id=workflow_result_id('tools'),
        can_manage=lambda: _has_access(
            dependencies.principal_provider(),
            TOOLS_MANAGER_ACCESS_KEY,
        ),
        source_name=dependencies.tools_source_name,
        projection_name=dependencies.tools_projection_name,
    )
    kpi_context = _kpi_context(dependencies, actor_provider)
    kpi_definition_context = _kpi_definition_context(dependencies, actor_provider)
    return ManagerSurfaceDefinition(
        principal_provider=dependencies.principal_provider,
        groups=(
            ManagerModuleGroup(key='administration', title='Administración', order=5),
            ManagerModuleGroup(key='configuration', title='Configuraciones', order=10),
        ),
        modules=(
            dependencies.profiles_module,
            ManagerModule(
                key='navigation',
                group_key='configuration',
                title='Navegación',
                route='/navigation',
                order=20,
                description='Rutas, secciones y perfiles habilitados en la navegación de ADA.',
                layout=lambda _services: build_navigation_admin_configuration(navigation_context),
                history_preview_renderer=build_navigation_history_preview,
                source_key=dependencies.navigation_source.source_key,
                source_service=NAVIGATION_SOURCE_SERVICE,
                source_reader_service=NAVIGATION_SOURCE_READER_SERVICE,
                source_history_service=NAVIGATION_SOURCE_HISTORY_SERVICE,
                projection_service=NAVIGATION_PROJECTION_SERVICE,
                draft_validation_service=NAVIGATION_DRAFT_VALIDATION_SERVICE,
                access_key=NAVIGATION_MANAGER_ACCESS_KEY,
                web_module=create_navigation_admin_web_module(navigation_context),
                source_name=dependencies.navigation_source_name,
                projection_name=dependencies.navigation_projection_name,
            ),
            ManagerModule(
                key='tools',
                group_key='configuration',
                title='Herramienta',
                route='/tools',
                order=30,
                description='Configuración de la herramienta operacional de esta aplicación.',
                layout=lambda _services: build_tool_manager_configuration(tools_context),
                history_preview_renderer=build_tool_history_preview,
                source_key=dependencies.tools_source.source_key,
                source_service=TOOLS_SOURCE_SERVICE,
                source_reader_service=TOOLS_SOURCE_READER_SERVICE,
                source_history_service=TOOLS_SOURCE_HISTORY_SERVICE,
                projection_service=TOOLS_PROJECTION_SERVICE,
                draft_validation_service=TOOLS_DRAFT_VALIDATION_SERVICE,
                access_key=TOOLS_MANAGER_ACCESS_KEY,
                web_module=create_tool_manager_web_module(tools_context),
                source_name=dependencies.tools_source_name,
                projection_name=dependencies.tools_projection_name,
            ),
            *_kpi_modules(kpi_context, dependencies),
            *_kpi_definition_modules(kpi_definition_context, dependencies),
        ),
        entries=(dependencies.users_entry,),
        route_prefix=MANAGER_ROUTE_PREFIX,
        web_modules=(
            create_bootstrap_web_module(),
            WebModule(
                name='ada-configuration-manager-services',
                register_services=lambda services: _register_services(services, dependencies),
            ),
        ),
    )


def _register_services(
    services: ServiceRegistry,
    dependencies: ConfigurationManagerDependencies,
) -> None:
    def actor_provider() -> str:
        return dependencies.principal_provider().subject_id

    navigation_source = NavigationManagerSourceWorkflow(
        source=dependencies.navigation_source,
        audit_actor_provider=actor_provider,
    )
    _register_source_workflow(
        services,
        workflow=navigation_source,
        source_service=NAVIGATION_SOURCE_SERVICE,
        source_reader_service=NAVIGATION_SOURCE_READER_SERVICE,
        source_history_service=NAVIGATION_SOURCE_HISTORY_SERVICE,
    )
    services.add(
        NAVIGATION_DRAFT_VALIDATION_SERVICE,
        NavigationManagerDraftValidationWorkflow(audit_actor_provider=actor_provider),
    )
    services.add(NAVIGATION_PROJECTION_SERVICE, dependencies.navigation_projection)

    tools_source = ToolManagerSourceWorkflow(
        source=dependencies.tools_source,
        audit_actor_provider=actor_provider,
    )
    _register_source_workflow(
        services,
        workflow=tools_source,
        source_service=TOOLS_SOURCE_SERVICE,
        source_reader_service=TOOLS_SOURCE_READER_SERVICE,
        source_history_service=TOOLS_SOURCE_HISTORY_SERVICE,
    )
    services.add(
        TOOLS_DRAFT_VALIDATION_SERVICE,
        ToolManagerDraftValidationWorkflow(audit_actor_provider=actor_provider),
    )
    services.add(TOOLS_PROJECTION_SERVICE, dependencies.tools_projection)

    if (
        dependencies.kpis_source is not None
        and dependencies.kpis_projection is not None
        and dependencies.kpi_destinations is not None
    ):
        kpi_source = KpiConfigurationManagerSourceWorkflow(
            source=dependencies.kpis_source,
            audit_actor_provider=actor_provider,
        )
        _register_source_workflow(
            services,
            workflow=kpi_source,
            source_service=KPI_SOURCE_SERVICE,
            source_reader_service=KPI_SOURCE_READER_SERVICE,
            source_history_service=KPI_SOURCE_HISTORY_SERVICE,
        )
        services.add(
            KPI_DRAFT_VALIDATION_SERVICE,
            KpiConfigurationManagerDraftValidationWorkflow(
                destinations=dependencies.kpi_destinations,
                audit_actor_provider=actor_provider,
            ),
        )
        services.add(KPI_PROJECTION_SERVICE, dependencies.kpis_projection)

    if (
        dependencies.kpi_definitions_source is not None
        and dependencies.kpi_definitions_projection is not None
        and dependencies.kpi_configuration_projection is not None
        and dependencies.kpis_source is not None
    ):
        definition_source = KpiDefinitionManagerSourceWorkflow(
            source=dependencies.kpi_definitions_source,
            audit_actor_provider=actor_provider,
        )
        _register_source_workflow(
            services,
            workflow=definition_source,
            source_service=KPI_DEFINITION_SOURCE_SERVICE,
            source_reader_service=KPI_DEFINITION_SOURCE_READER_SERVICE,
            source_history_service=KPI_DEFINITION_SOURCE_HISTORY_SERVICE,
        )
        services.add(
            KPI_DEFINITION_DRAFT_VALIDATION_SERVICE,
            KpiDefinitionManagerDraftValidationWorkflow(
                kpi_configuration_projection=dependencies.kpi_configuration_projection,
                kpi_configuration_source_key=dependencies.kpis_source.source_key,
                audit_actor_provider=actor_provider,
            ),
        )
        services.add(KPI_DEFINITION_PROJECTION_SERVICE, dependencies.kpi_definitions_projection)


def _register_source_workflow(
    services: ServiceRegistry,
    *,
    workflow: object,
    source_service: str,
    source_reader_service: str,
    source_history_service: str,
) -> None:
    services.add(source_service, workflow)
    services.add(source_reader_service, workflow)
    services.add(source_history_service, workflow)


def _has_access(principal: ManagerPrincipal, access_key: str) -> bool:
    return access_key in principal.access_keys


def _kpi_context(
    dependencies: ConfigurationManagerDependencies,
    actor_provider: Callable[[], str],
) -> KpiManagerWebContext | None:
    if dependencies.kpis_source is None or dependencies.kpi_destinations is None:
        return None
    workspace = ManagerWorkspaceBridge(
        owner_subject_id_provider=actor_provider,
        source_snapshot_provider=dependencies.kpis_source.get_current,
    )
    return KpiManagerWebContext(
        destinations=dependencies.kpi_destinations,
        workspace_payload_reader=workspace.read_payload,
        workspace_payload_writer=workspace.write_payload,
        draft_store_id=workflow_draft_id('kpis'),
        saved_draft_store_id=workflow_saved_draft_id('kpis'),
        draft_save_action_id=workflow_action_id('kpis', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('kpis'),
        result_id=workflow_result_id('kpis'),
        can_manage=lambda: _has_access(
            dependencies.principal_provider(),
            KPI_MANAGER_ACCESS_KEY,
        ),
        source_name=dependencies.kpis_source_name,
        projection_name=dependencies.kpis_projection_name,
    )


def _kpi_modules(
    context: KpiManagerWebContext | None,
    dependencies: ConfigurationManagerDependencies,
) -> tuple[ManagerModule, ...]:
    if context is None or dependencies.kpis_source is None:
        return ()
    return (
        ManagerModule(
            key='kpis',
            group_key='configuration',
            title='KPI',
            route='/kpis',
            order=40,
            description='Configuración de KPI y sus destinos de consumo en ADA.',
            layout=lambda _services: build_kpi_manager_configuration(context),
            history_preview_renderer=build_kpi_history_preview,
            source_key=dependencies.kpis_source.source_key,
            source_service=KPI_SOURCE_SERVICE,
            source_reader_service=KPI_SOURCE_READER_SERVICE,
            source_history_service=KPI_SOURCE_HISTORY_SERVICE,
            projection_service=KPI_PROJECTION_SERVICE,
            draft_validation_service=KPI_DRAFT_VALIDATION_SERVICE,
            access_key=KPI_MANAGER_ACCESS_KEY,
            web_module=create_kpi_manager_web_module(context),
            source_name=dependencies.kpis_source_name,
            projection_name=dependencies.kpis_projection_name,
        ),
    )


def _kpi_definition_context(
    dependencies: ConfigurationManagerDependencies,
    actor_provider: Callable[[], str],
) -> KpiDefinitionManagerWebContext | None:
    if (
        dependencies.kpi_definitions_source is None
        or dependencies.kpi_configuration_projection is None
        or dependencies.kpis_source is None
    ):
        return None
    workspace = ManagerWorkspaceBridge(
        owner_subject_id_provider=actor_provider,
        source_snapshot_provider=dependencies.kpi_definitions_source.get_current,
    )
    return KpiDefinitionManagerWebContext(
        kpi_configuration_projection=dependencies.kpi_configuration_projection,
        kpi_configuration_source_key=dependencies.kpis_source.source_key,
        workspace_payload_reader=workspace.read_payload,
        workspace_payload_writer=workspace.write_payload,
        draft_store_id=workflow_draft_id('kpi-definitions'),
        saved_draft_store_id=workflow_saved_draft_id('kpi-definitions'),
        draft_save_action_id=workflow_action_id('kpi-definitions', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('kpi-definitions'),
        result_id=workflow_result_id('kpi-definitions'),
        can_manage=lambda: _has_access(
            dependencies.principal_provider(),
            KPI_MANAGER_ACCESS_KEY,
        ),
        source_name=dependencies.kpi_definitions_source_name,
        projection_name=dependencies.kpi_definitions_projection_name,
    )


def _kpi_definition_modules(
    context: KpiDefinitionManagerWebContext | None,
    dependencies: ConfigurationManagerDependencies,
) -> tuple[ManagerModule, ...]:
    if context is None or dependencies.kpi_definitions_source is None:
        return ()
    return (
        ManagerModule(
            key='kpi-definitions',
            group_key='configuration',
            title='Definiciones KPI',
            route='/kpi-definitions',
            order=50,
            description='Información descriptiva asociada a los KPI configurados en ADA.',
            layout=lambda _services: build_kpi_definition_manager_configuration(context),
            history_preview_renderer=build_kpi_definition_history_preview,
            source_key=dependencies.kpi_definitions_source.source_key,
            source_service=KPI_DEFINITION_SOURCE_SERVICE,
            source_reader_service=KPI_DEFINITION_SOURCE_READER_SERVICE,
            source_history_service=KPI_DEFINITION_SOURCE_HISTORY_SERVICE,
            projection_service=KPI_DEFINITION_PROJECTION_SERVICE,
            draft_validation_service=KPI_DEFINITION_DRAFT_VALIDATION_SERVICE,
            access_key=KPI_MANAGER_ACCESS_KEY,
            web_module=create_kpi_definition_manager_web_module(context),
            source_name=dependencies.kpi_definitions_source_name,
            projection_name=dependencies.kpi_definitions_projection_name,
        ),
    )
