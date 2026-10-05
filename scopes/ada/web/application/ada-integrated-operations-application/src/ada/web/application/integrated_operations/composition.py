from ada.contracts.tools.enums import ToolConfigurationKind
from ada.web.application.generic import AdaApplicationExtension
from ada.web.application.integrated_operations.modules.dashboard import create_dashboard_module
from ada.web.operational_render_binding import OperationalRenderBinding


def create_integrated_operations_extension(
    binding: OperationalRenderBinding | None,
) -> AdaApplicationExtension:
    if binding is not None and binding.structure.kind is not ToolConfigurationKind.INTEGRATED_OPERATIONS:
        raise ValueError('Integrated Operations application requires an Integrated Operations Tool')
    return AdaApplicationExtension(
        modules=(create_dashboard_module(binding),),
        page_packages=(),
    )
