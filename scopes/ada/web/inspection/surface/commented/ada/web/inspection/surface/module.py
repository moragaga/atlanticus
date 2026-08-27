from __future__ import annotations

from ada.web.inspection.surface.markup import build_kpi_inspection_surface_fragment
from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule

# Carga después de las capas UI/shell actuales y sigue siendo una capability independiente.
ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER = AssetLayer(
    name='ada_kpi_inspection_surface',
    load_order=300,
    package='ada.web.inspection.surface',
)


def create_kpi_inspection_surface_module(
    *,
    api_base_path: str = '/api/inspection/kpis',
) -> WebModule:
    normalized = api_base_path.strip().rstrip('/')
    if not normalized.startswith('/') or normalized == '/':
        raise ValueError('API base path must be an absolute non-root path')
    # El endpoint se publica como configuración pública; el JS no conoce Flask ni un host concreto.
    return WebModule(
        name='kpi-inspection-surface',
        asset_layers=(ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER,),
        index=IndexContribution(
            body_end_fragments=(build_kpi_inspection_surface_fragment(),),
            runtime_config={'api_base_path': normalized},
        ),
    )
