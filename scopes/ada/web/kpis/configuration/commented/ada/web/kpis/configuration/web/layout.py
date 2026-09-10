from __future__ import annotations

from dash import dcc, html

from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiDestinationCatalog,
)
from ada.web.kpis.configuration.web.ids import (
    CONFIGURATION_STORE_ID,
    EDITOR_STORE_ID,
    QUERY_STORE_ID,
)
from ada.web.kpis.configuration.web.models import KpiConfigurationEditorContext
from ada.web.kpis.configuration.web.presentation import (
    build_kpi_configuration_editor,
)
from ada.web.kpis.configuration.web.query import (
    KpiConfigurationQuery,
    query_kpi_configuration,
)


def build_kpi_configuration_editor_surface(
    context: KpiConfigurationEditorContext,
) -> object:
    configuration = KpiConfiguration()
    query = KpiConfigurationQuery()
    loaded = _load_catalog(context)
    catalog = _resolved_catalog(loaded)
    creation_enabled, reason = creation_state(loaded)
    page = query_kpi_configuration(configuration, query)

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
            build_kpi_configuration_editor(
                page,
                destination_catalog=catalog,
                query=query,
                creation_enabled=creation_enabled,
                creation_disabled_reason=reason,
                can_manage=context.can_manage(),
            ),
        ],
        className='ada-kpi-configuration-editor-surface',
    )


def load_catalog(
    context: KpiConfigurationEditorContext,
) -> KpiDestinationCatalog | None:
    return _load_catalog(context)


def resolved_catalog(
    catalog: KpiDestinationCatalog | None,
) -> KpiDestinationCatalog:
    return _resolved_catalog(catalog)


def creation_state(
    catalog: KpiDestinationCatalog | None,
) -> tuple[bool, str | None]:
    if catalog is None:
        return False, 'La proyección de Herramienta no está disponible.'
    system = {'global_indicators', 'time_status'}
    if not any(destination.key not in system for destination in catalog.destinations):
        return (
            False,
            'Configura al menos un componente en Herramienta antes de crear KPI.',
        )
    return True, None


def query_document(query: KpiConfigurationQuery) -> dict[str, object]:
    return {
        'search': query.search,
        'destination_keys': list(query.destination_keys),
        'data_mode': query.data_mode.value,
        'sort_field': query.sort_field.value,
        'sort_direction': query.sort_direction.value,
        'page_number': query.page.page_number,
        'page_size': query.page.page_size,
    }


def _load_catalog(
    context: KpiConfigurationEditorContext,
) -> KpiDestinationCatalog | None:
    try:
        return context.destinations.load()
    except Exception:
        return None


def _resolved_catalog(
    catalog: KpiDestinationCatalog | None,
) -> KpiDestinationCatalog:
    if catalog is not None:
        return catalog
    return KpiDestinationCatalog(
        tool_projection_revision='unavailable',
        destinations=(),
    )
