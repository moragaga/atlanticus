# Espejo comentado: API del runtime de Global Indicators propiedad del Dashboard IO.
from .bindings import (
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
)
from .catalog import INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS
from .resolver import (
    ResolvedDashboardGlobalIndicator,
    resolve_dashboard_global_indicators,
)
from .runtime import (
    GLOBAL_INDICATORS_DESTINATION_KEY,
    build_dashboard_global_indicators_runtime_component,
    create_dashboard_global_indicators_module,
)

__all__ = [
    'GLOBAL_INDICATORS_DESTINATION_KEY',
    'INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS',
    'DashboardGlobalIndicatorBinding',
    'DashboardGlobalIndicatorsRuntimeBinding',
    'ResolvedDashboardGlobalIndicator',
    'build_dashboard_global_indicators_runtime_component',
    'create_dashboard_global_indicators_module',
    'resolve_dashboard_global_indicators',
]
