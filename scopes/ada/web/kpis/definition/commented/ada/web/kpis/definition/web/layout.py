# Espejo pedagógico del contrato productivo.
# La implementación conserva las mismas clases y funciones; estos comentarios explican la intención general.
# Definition consume directamente la proyección tipada de KPI Configuration y delega identidad/versionado a Atlanticus.
from __future__ import annotations

from dash import dcc, html

from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.definition import KpiDefinitionConfiguration
from ada.web.kpis.definition.web.ids import (
    CONFIGURATION_STORE_ID,
    EDITOR_STORE_ID,
    QUERY_STORE_ID,
)
from ada.web.kpis.definition.web.models import KpiDefinitionEditorContext
from ada.web.kpis.definition.web.presentation import build_kpi_definition_editor
from ada.web.kpis.definition.web.query import KpiDefinitionQuery, query_kpi_definitions


def build_kpi_definition_editor_surface(
    context: KpiDefinitionEditorContext,
) -> object:
    configuration = KpiDefinitionConfiguration()
    query = KpiDefinitionQuery()
    kpi_registry = load_kpi_registry(context)
    page = query_kpi_definitions(configuration, kpi_registry, query)
    return html.Div(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=configuration.to_document(),
                storage_type='memory',
            ),
            dcc.Store(
                id=QUERY_STORE_ID,
                data=query_document(query),
                storage_type='memory',
            ),
            dcc.Store(id=EDITOR_STORE_ID, storage_type='memory'),
            build_kpi_definition_editor(
                page,
                query=query,
                kpi_registry=kpi_registry,
                can_manage=context.can_manage(),
            ),
        ],
        className='ada-kpi-definition-editor-surface',
    )


def load_kpi_registry(
    context: KpiDefinitionEditorContext,
) -> KpiRegistry | None:
    try:
        projection = context.kpi_registry_projection.get_active(
            context.kpi_registry_source_key
        )
    except Exception:
        return None
    if projection is None or not isinstance(projection.payload, KpiRegistry):
        return None
    return projection.payload


def query_document(query: KpiDefinitionQuery) -> dict[str, object]:
    return {
        'search': query.search,
        'status': query.status.value,
        'page_number': query.page.page_number,
        'page_size': query.page.page_size,
    }
