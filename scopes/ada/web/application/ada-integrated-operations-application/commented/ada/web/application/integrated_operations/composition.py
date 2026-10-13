# Espejo comentado: IO compone Dashboard y un único runtime de Global Indicators para el catálogo.
from ada.contracts.tools.enums import ToolConfigurationKind
from ada.web.application.generic import AdaApplicationExtension
from ada.web.application.integrated_operations.modules.dashboard import create_dashboard_module
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
    create_dashboard_global_indicators_module,
)
from ada.web.application.integrated_operations.modules.dashboard.global_indicators.catalog import (
    INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS,
    INTEGRATED_OPERATIONS_GLOBAL_INDICATORS_CONTENT_STATE,
)
from ada.web.application.integrated_operations.modules.dashboard.time_status import (
    DashboardTimeStatusSourceBinding,
    INTEGRATED_OPERATIONS_TIME_STATUS_SOURCES,
    create_dashboard_time_status_detail_provider,
)
from ada.web.operational_render_binding import OperationalRenderBinding


def create_integrated_operations_extension(
    binding: OperationalRenderBinding | None,
    *,
    global_indicator_bindings: tuple[DashboardGlobalIndicatorBinding, ...] | None = None,
    time_status_sources: tuple[DashboardTimeStatusSourceBinding, ...] | None = None,
) -> AdaApplicationExtension:
    if (
        binding is not None
        and binding.structure.kind is not ToolConfigurationKind.INTEGRATED_OPERATIONS
    ):
        raise ValueError('Integrated Operations application requires an Integrated Operations Tool')
    resolved_global_indicator_bindings = (
        INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS
        if global_indicator_bindings is None
        else global_indicator_bindings
    )
    if not isinstance(resolved_global_indicator_bindings, tuple):
        raise TypeError('global_indicator_bindings must be a tuple')
    resolved_time_status_sources = (
        INTEGRATED_OPERATIONS_TIME_STATUS_SOURCES
        if time_status_sources is None else time_status_sources
    )
    if not isinstance(resolved_time_status_sources, tuple):
        raise TypeError('time_status_sources must be a tuple')
    modules = [create_dashboard_module(binding)]
    # Sin Tool READY no existe identidad de Store y el runtime no se monta.
    if resolved_global_indicator_bindings and binding is not None:
        modules.append(
            create_dashboard_global_indicators_module(
                DashboardGlobalIndicatorsRuntimeBinding(
                    tool_key=binding.structure.tool_key,
                    indicators=resolved_global_indicator_bindings,
                    # El estado pertenece al conjunto completo inyectado al runtime.
                    content_state=INTEGRATED_OPERATIONS_GLOBAL_INDICATORS_CONTENT_STATE,
                )
            )
        )
    detail = (
        None
        if binding is None or not resolved_time_status_sources
        else create_dashboard_time_status_detail_provider(
            binding.structure.tool_key,
            resolved_time_status_sources,
        )
    )
    return AdaApplicationExtension(
        modules=tuple(modules),
        page_packages=(),
        time_status_detail=detail,
    )
