# Espejo pedagógico del contrato productivo.
# La implementación conserva las mismas clases y funciones; estos comentarios explican la intención general.
# Definition consume directamente la proyección tipada de KPI Configuration y delega identidad/versionado a Atlanticus.
from ada.web.kpis.definition.configuration.web.callbacks import (
    delete_definition,
    parse_configuration,
    parse_query,
    register_kpi_definition_editor_callbacks,
    save_definition_detail,
)
from ada.web.kpis.definition.configuration.web.layout import (
    build_kpi_definition_editor_surface,
    load_kpi_registry,
)
from ada.web.kpis.definition.configuration.web.models import KpiDefinitionEditorContext
from ada.web.kpis.definition.configuration.web.module import (
    ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER,
    create_kpi_definition_editor_module,
)
from ada.web.kpis.definition.configuration.web.presentation import (
    build_kpi_definition_detail_view,
    build_kpi_definition_editor,
    build_kpi_definition_grid,
    build_kpi_definition_modal,
)
from ada.web.kpis.definition.configuration.web.query import (
    KpiDefinitionEditorItem,
    KpiDefinitionEditorStatus,
    KpiDefinitionQuery,
    KpiDefinitionStatusFilter,
    build_kpi_definition_editor_items,
    query_kpi_definitions,
)

__all__ = [
    'ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER',
    'KpiDefinitionEditorContext',
    'KpiDefinitionEditorItem',
    'KpiDefinitionEditorStatus',
    'KpiDefinitionQuery',
    'KpiDefinitionStatusFilter',
    'build_kpi_definition_detail_view',
    'build_kpi_definition_editor',
    'build_kpi_definition_editor_items',
    'build_kpi_definition_editor_surface',
    'build_kpi_definition_grid',
    'build_kpi_definition_modal',
    'create_kpi_definition_editor_module',
    'delete_definition',
    'load_kpi_registry',
    'parse_configuration',
    'parse_query',
    'query_kpi_definitions',
    'register_kpi_definition_editor_callbacks',
    'save_definition_detail',
]
