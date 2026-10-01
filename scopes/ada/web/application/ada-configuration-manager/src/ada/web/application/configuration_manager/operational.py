from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada.web.application.configuration_manager.operational_callbacks import (
    register_operational_callbacks,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE,
    OPERATIONAL_CATALOG_PROJECTION_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_READER_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_SERVICE,
    OperationalCatalogDraftEditor,
)
from ada.web.application.configuration_manager.operational_layout import (
    _position_options,
    build_operational_assignments,
    build_operational_catalog_configuration,
    build_operational_catalog_history_preview,
)
from ada.web.operational.identification import CATALOG_SOURCE_KEY, OperationalIdentificationService
from atlanticus.web.assets import AssetLayer
from atlanticus.web.manager import (
    ManagerCompanionView,
    ManagerModule,
    ManagerPrincipal,
    manager_access_granted,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.users.models import UserRecord

OPERATIONAL_MANAGER_ACCESS_KEY = 'operational.manage'
OPERATIONAL_MANAGER_ASSETS = AssetLayer(
    name='ada_configuration_manager_operational',
    load_order=740,
    package='ada.web.application.configuration_manager',
    resource_directory='resources/operational',
)


@dataclass(frozen=True, slots=True)
class OperationalAssignmentContext:
    service: OperationalIdentificationService
    promoted_users: Callable[[], tuple[UserRecord, ...]]
    principal: Callable[[], ManagerPrincipal]

    def can_manage(self) -> bool:
        return manager_access_granted(self.principal(), OPERATIONAL_MANAGER_ACCESS_KEY)


@dataclass(frozen=True, slots=True)
class OperationalCatalogManagerWebContext:
    editor: OperationalCatalogDraftEditor
    current_payload_provider: Callable[[], dict[str, object] | None]
    workspace_payload_reader: Callable[[dict[str, object] | None], dict[str, object] | None]
    workspace_payload_writer: Callable[[dict[str, object] | None, dict[str, object]], dict[str, object]]
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    result_id: object
    can_manage: Callable[[], bool]


def create_operational_manager_module(
    *,
    catalog_context: OperationalCatalogManagerWebContext,
    assignment_context: OperationalAssignmentContext,
    source_name: str = 'Source',
    projection_name: str = 'Projection',
) -> ManagerModule:
    web_module = WebModule(
        name='ada-operational-identification-manager',
        asset_layers=(OPERATIONAL_MANAGER_ASSETS,),
        register_callbacks=lambda app, _services: register_operational_callbacks(
            app,
            catalog_context,
            assignment_context,
        ),
    )
    return ManagerModule(
        key='operational-identification',
        group_key='administration',
        title='Datos operacionales',
        route='/operational-identification',
        order=15,
        description='Cargos y asignaciones operacionales de usuarios promovidos.',
        layout=lambda _services: build_operational_catalog_configuration(catalog_context),
        history_preview_renderer=build_operational_catalog_history_preview,
        source_key=CATALOG_SOURCE_KEY,
        source_service=OPERATIONAL_CATALOG_SOURCE_SERVICE,
        source_reader_service=OPERATIONAL_CATALOG_SOURCE_READER_SERVICE,
        source_history_service=OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE,
        projection_service=OPERATIONAL_CATALOG_PROJECTION_SERVICE,
        draft_validation_service=OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE,
        access_key=OPERATIONAL_MANAGER_ACCESS_KEY,
        web_module=web_module,
        source_name=source_name,
        projection_name=projection_name,
        companion_view=ManagerCompanionView(
            title='Asignaciones',
            layout=lambda _services: build_operational_assignments(assignment_context),
        ),
        primary_view_title='Catálogo de cargos',
        default_primary_view='companion',
    )


__all__ = [
    'OPERATIONAL_MANAGER_ACCESS_KEY',
    'OperationalAssignmentContext',
    'OperationalCatalogManagerWebContext',
    '_position_options',
    'build_operational_assignments',
    'build_operational_catalog_configuration',
    'build_operational_catalog_history_preview',
    'create_operational_manager_module',
    'register_operational_callbacks',
]
