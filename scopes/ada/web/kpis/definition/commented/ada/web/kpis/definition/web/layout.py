# Espejo comentado de la superficie Web de KPI Definition.
from __future__ import annotations

from dash import dcc, html

from ada.web.kpis.definition import KpiDefinitionAuthorityCatalog, KpiDefinitionConfiguration
from ada.web.kpis.definition.web.ids import (
    CONFIGURATION_STORE_ID,
    EDITOR_STORE_ID,
    QUERY_STORE_ID,
)
from ada.web.kpis.definition.web.models import KpiDefinitionEditorContext
from ada.web.kpis.definition.web.presentation import build_kpi_definition_editor
from ada.web.kpis.definition.web.query import (
    KpiDefinitionQuery,
    query_kpi_definitions,
)


def build_kpi_definition_editor_surface(
    context: KpiDefinitionEditorContext,
) -> object:
    configuration = KpiDefinitionConfiguration()
    query = KpiDefinitionQuery()
    authority = load_authority(context)
    page = query_kpi_definitions(configuration, authority, query)

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
                authority=authority,
                can_manage=context.can_manage(),
            ),
        ],
        className='ada-kpi-definition-editor-surface',
    )


def load_authority(
    context: KpiDefinitionEditorContext,
) -> KpiDefinitionAuthorityCatalog | None:
    try:
        return context.authority.load()
    except Exception:
        return None


def query_document(query: KpiDefinitionQuery) -> dict[str, object]:
    return {
        'search': query.search,
        'status': query.status.value,
        'page_number': query.page.page_number,
        'page_size': query.page.page_size,
    }
