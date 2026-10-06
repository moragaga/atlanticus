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
)
from ada.web.operational_render_binding import OperationalRenderBinding


def create_integrated_operations_extension(
    binding: OperationalRenderBinding | None,
    *,
    global_indicator_bindings: tuple[DashboardGlobalIndicatorBinding, ...] | None = None,
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
    modules = [create_dashboard_module(binding)]
    if resolved_global_indicator_bindings:
        if binding is None:
            raise ValueError('Global Indicators require an Operational Render Binding')
        modules.append(
            create_dashboard_global_indicators_module(
                DashboardGlobalIndicatorsRuntimeBinding(
                    tool_key=binding.structure.tool_key,
                    indicators=resolved_global_indicator_bindings,
                )
            )
        )
    return AdaApplicationExtension(
        modules=tuple(modules),
        page_packages=(),
    )
