from __future__ import annotations

import logging

from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinitionSnapshotStore
from ada.web.inspection.providers.kpi_definition import KpiDefinitionProjectionProvider
from ada.web.inspection.surface import create_kpi_inspection_surface_module
from ada.web.kpis.definition.configuration import KPI_DEFINITION_SOURCE_KEY
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from atlanticus.web.modules import WebModule
from atlanticus.web.projection.store import ProjectionStore

_LOGGER = logging.getLogger(__name__)


def create_kpi_inspection_modules(
    projection_store: ProjectionStore[KpiDefinitionCatalog],
    *,
    unavailable_errors: tuple[type[Exception], ...] = (),
) -> tuple[WebModule, ...]:
    if not isinstance(projection_store, ProjectionStore):
        raise TypeError('KPI Inspection projection store must implement ProjectionStore')
    if not isinstance(unavailable_errors, tuple) or any(
        not isinstance(error, type) or not issubclass(error, Exception)
        for error in unavailable_errors
    ):
        raise TypeError('KPI Inspection unavailable errors must be exception types')

    provider = KpiDefinitionProjectionProvider(
        projection_store=projection_store,
        source_key=KPI_DEFINITION_SOURCE_KEY,
    )
    snapshot_store = KpiDefinitionSnapshotStore()
    try:
        snapshot_store.replace(provider.load_snapshot())
    except unavailable_errors as error:
        _LOGGER.warning('KPI Inspection definitions unavailable (%s)', type(error).__name__)

    return (
        create_kpi_inspection_api_module(snapshot_store),
        create_kpi_inspection_surface_module(),
    )
