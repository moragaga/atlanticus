# Espejo comentado: IO compone Dashboard y, cuando existen definiciones, su runtime de Global Indicators.
from ada.contracts.tools.enums import ToolConfigurationKind
from ada.web.application.generic import AdaApplicationExtension
from ada.web.application.integrated_operations.modules.dashboard import create_dashboard_module
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
    create_dashboard_global_indicators_module,
)
from ada.web.operational_render_binding import OperationalRenderBinding


def create_integrated_operations_extension(
    binding: OperationalRenderBinding | None,
    *,
    global_indicator_bindings: tuple[DashboardGlobalIndicatorBinding, ...] = (),
) -> AdaApplicationExtension:
    if (
        binding is not None
        and binding.structure.kind is not ToolConfigurationKind.INTEGRATED_OPERATIONS
    ):
        raise ValueError('Integrated Operations application requires an Integrated Operations Tool')
    if not isinstance(global_indicator_bindings, tuple):
        raise TypeError('global_indicator_bindings must be a tuple')
    modules = [create_dashboard_module(binding)]
    if global_indicator_bindings:
        if binding is None:
            raise ValueError('Global Indicators require an Operational Render Binding')
        # El Dashboard aporta sólo scopes de presentación; valores y envelopes vienen del Collector.
        modules.append(
            create_dashboard_global_indicators_module(
                DashboardGlobalIndicatorsRuntimeBinding(
                    tool_key=binding.structure.tool_key,
                    indicators=global_indicator_bindings,
                )
            )
        )
    return AdaApplicationExtension(
        modules=tuple(modules),
        page_packages=(),
    )
