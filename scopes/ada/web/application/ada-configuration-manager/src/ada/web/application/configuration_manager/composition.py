from __future__ import annotations

from ada.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
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
    KpiConfigurationManagerWorkflowAdapter,
    NavigationManagerWorkflowAdapter,
    ToolConfigurationManagerWorkflowAdapter,
    UsersManagerWorkflowAdapter,
)
from atlanticus.web.bootstrap import create_bootstrap_web_module
from atlanticus.web.manager import (
    ManagerModule,
    ManagerModuleAccess,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_refresh_signal_id,
    workflow_result_id,
    workflow_saved_draft_id,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.configuration import NavigationProfileOption
from atlanticus.web.navigation.configuration.web import (
    NavigationAdminWebContext,
    build_navigation_admin_configuration,
    build_navigation_history_preview,
    create_navigation_admin_web_module,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.configuration.web import (
    UsersAdminWebContext,
    build_users_admin_configuration,
    build_users_history_preview,
    create_users_admin_web_module,
)

MANAGER_ROUTE_PREFIX = '/manager'

USERS_WORKFLOW_SERVICE = 'ada.configuration-manager.users.workflow'
NAVIGATION_WORKFLOW_SERVICE = 'ada.configuration-manager.navigation.workflow'
TOOLS_WORKFLOW_SERVICE = 'ada.configuration-manager.tools.workflow'
KPI_WORKFLOW_SERVICE = 'ada.configuration-manager.kpis.workflow'


def build_configuration_manager_surface(
    dependencies: ConfigurationManagerDependencies,
) -> ManagerSurfaceDefinition:
    users_context = UsersAdminWebContext(
        services=dependencies.users,
        draft_store_id=workflow_draft_id('users'),
        saved_draft_store_id=workflow_saved_draft_id('users'),
        draft_save_action_id=workflow_action_id('users', 'save-draft'),
        workflow_refresh_signal_id=workflow_refresh_signal_id('users'),
        editor_revision_store_id=workflow_editor_revision_id('users'),
        draft_owner_provider=lambda: dependencies.principal_provider().subject_id,
        can_manage=lambda: _can_manage_users(dependencies.principal_provider()),
        source_name=dependencies.users_source_name,
        projection_name=dependencies.users_projection_name,
    )
    navigation_context = NavigationAdminWebContext(
        services=dependencies.navigation,
        draft_store_id=workflow_draft_id('navigation'),
        saved_draft_store_id=workflow_saved_draft_id('navigation'),
        draft_save_action_id=workflow_action_id('navigation', 'save-draft'),
        workflow_refresh_signal_id=workflow_refresh_signal_id('navigation'),
        editor_revision_store_id=workflow_editor_revision_id('navigation'),
        draft_owner_provider=lambda: dependencies.principal_provider().subject_id,
        can_manage=lambda: _can_manage_navigation(dependencies.principal_provider()),
        source_name=dependencies.navigation_source_name,
        projection_name=dependencies.navigation_projection_name,
        profile_options_provider=lambda: _navigation_profile_options(dependencies),
    )
    tools_context = ToolManagerWebContext(
        draft_store_id=workflow_draft_id('tools'),
        saved_draft_store_id=workflow_saved_draft_id('tools'),
        draft_save_action_id=workflow_action_id('tools', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('tools'),
        result_id=workflow_result_id('tools'),
        draft_owner_provider=lambda: dependencies.principal_provider().subject_id,
        can_manage=lambda: _can_manage_tools(dependencies.principal_provider()),
        source_name=dependencies.tools_source_name,
        projection_name=dependencies.tools_projection_name,
    )
    kpi_context = _kpi_context(dependencies)
    return ManagerSurfaceDefinition(
        principal_provider=dependencies.principal_provider,
        groups=(
            ManagerModuleGroup(
                key='configuration',
                title='Configuraciones',
                order=10,
            ),
        ),
        modules=(
            ManagerModule(
                key='users',
                group_key='configuration',
                title='Usuarios',
                route='/users',
                order=10,
                description='Perfiles, usuarios y acceso administrativo de ADA.',
                layout=lambda _services: build_users_admin_configuration(users_context),
                history_preview_renderer=build_users_history_preview,
                workflow_service=USERS_WORKFLOW_SERVICE,
                access=ManagerModuleAccess(
                    view='users.manage',
                    validate='users.manage',
                    project='users.manage',
                    publish='users.manage',
                ),
                web_module=create_users_admin_web_module(users_context),
                source_name=dependencies.users_source_name,
                projection_name=dependencies.users_projection_name,
                force_publish_enabled=dependencies.force_publish_enabled,
            ),
            ManagerModule(
                key='navigation',
                group_key='configuration',
                title='Navegación',
                route='/navigation',
                order=20,
                description='Rutas, secciones y perfiles habilitados en la navegación de ADA.',
                layout=lambda _services: build_navigation_admin_configuration(navigation_context),
                history_preview_renderer=build_navigation_history_preview,
                workflow_service=NAVIGATION_WORKFLOW_SERVICE,
                access=ManagerModuleAccess(
                    view='navigation.manage',
                    validate='navigation.manage',
                    project='navigation.manage',
                    publish='navigation.manage',
                ),
                web_module=create_navigation_admin_web_module(navigation_context),
                source_name=dependencies.navigation_source_name,
                projection_name=dependencies.navigation_projection_name,
                force_publish_enabled=dependencies.force_publish_enabled,
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
                workflow_service=TOOLS_WORKFLOW_SERVICE,
                access=ManagerModuleAccess(
                    view='tools.manage',
                    validate='tools.manage',
                    project='tools.manage',
                    publish='tools.manage',
                ),
                web_module=create_tool_manager_web_module(tools_context),
                source_name=dependencies.tools_source_name,
                projection_name=dependencies.tools_projection_name,
                force_publish_enabled=dependencies.force_publish_enabled,
            ),
            *_kpi_modules(kpi_context, dependencies),
        ),
        route_prefix=MANAGER_ROUTE_PREFIX,
        web_modules=(
            create_bootstrap_web_module(),
            WebModule(
                name='ada-configuration-manager-services',
                register_services=lambda services: _register_services(
                    services,
                    dependencies,
                ),
            ),
        ),
    )


def _register_services(
    services: ServiceRegistry,
    dependencies: ConfigurationManagerDependencies,
) -> None:
    services.add(
        USERS_WORKFLOW_SERVICE,
        UsersManagerWorkflowAdapter(dependencies.users),
    )
    services.add(
        NAVIGATION_WORKFLOW_SERVICE,
        NavigationManagerWorkflowAdapter(dependencies.navigation),
    )
    services.add(
        TOOLS_WORKFLOW_SERVICE,
        ToolConfigurationManagerWorkflowAdapter(dependencies.tools),
    )
    if dependencies.kpis is not None:
        services.add(
            KPI_WORKFLOW_SERVICE,
            KpiConfigurationManagerWorkflowAdapter(dependencies.kpis),
        )


def _can_manage_users(principal: ManagerPrincipal) -> bool:
    return (
        principal.is_local
        or 'administrator' in principal.profile_keys
        or 'users.manage' in principal.access_keys
    )


def _can_manage_navigation(principal: ManagerPrincipal) -> bool:
    return (
        principal.is_local
        or 'administrator' in principal.profile_keys
        or 'navigation.manage' in principal.access_keys
    )


def _can_manage_tools(principal: ManagerPrincipal) -> bool:
    return (
        principal.is_local
        or 'administrator' in principal.profile_keys
        or 'tools.manage' in principal.access_keys
    )



def _can_manage_kpis(principal: ManagerPrincipal) -> bool:
    return (
        principal.is_local
        or 'administrator' in principal.profile_keys
        or 'kpis.manage' in principal.access_keys
    )


def _kpi_context(
    dependencies: ConfigurationManagerDependencies,
) -> KpiManagerWebContext | None:
    if dependencies.kpis is None or dependencies.kpi_destinations is None:
        return None
    return KpiManagerWebContext(
        destinations=dependencies.kpi_destinations,
        draft_store_id=workflow_draft_id('kpis'),
        saved_draft_store_id=workflow_saved_draft_id('kpis'),
        draft_save_action_id=workflow_action_id('kpis', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('kpis'),
        result_id=workflow_result_id('kpis'),
        draft_owner_provider=lambda: dependencies.principal_provider().subject_id,
        can_manage=lambda: _can_manage_kpis(dependencies.principal_provider()),
        source_name=dependencies.kpis_source_name,
        projection_name=dependencies.kpis_projection_name,
    )


def _kpi_modules(
    context: KpiManagerWebContext | None,
    dependencies: ConfigurationManagerDependencies,
) -> tuple[ManagerModule, ...]:
    if context is None:
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
            workflow_service=KPI_WORKFLOW_SERVICE,
            access=ManagerModuleAccess(
                view='kpis.manage',
                validate='kpis.manage',
                project='kpis.manage',
                publish='kpis.manage',
            ),
            web_module=create_kpi_manager_web_module(context),
            source_name=dependencies.kpis_source_name,
            projection_name=dependencies.kpis_projection_name,
            force_publish_enabled=dependencies.force_publish_enabled,
        ),
    )


def _navigation_profile_options(
    dependencies: ConfigurationManagerDependencies,
) -> tuple[NavigationProfileOption, ...]:
    users_catalog = dependencies.users.administration.load_catalog()
    if users_catalog is None:
        return ()
    profile_catalog = users_catalog.profile_catalog()
    return tuple(
        NavigationProfileOption(
            key=profile.key,
            label=profile.label,
            unrestricted=profile.key in {'local', 'administrator'},
            background_color=profile.background_color,
            text_color=profile.text_color,
        )
        for profile in profile_catalog.all()
    )
