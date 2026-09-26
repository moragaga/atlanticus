from __future__ import annotations

from ada.web.tools.enums import ToolConfigurationKind


# Establece la transición estricta entre niveles usando el enum canónico del catálogo Tool.
# La ausencia de siguiente nivel indica que la ruta debe finalizar aquí.
def next_routing_tool_kind(current_kind: ToolConfigurationKind) -> ToolConfigurationKind | None:
    if not isinstance(current_kind, ToolConfigurationKind):
        raise TypeError('current_kind must be a ToolConfigurationKind')
    # Process sólo puede escalar al nivel inmediatamente superior.
    if current_kind is ToolConfigurationKind.PROCESS:
        return ToolConfigurationKind.INTEGRATED_OPERATIONS
    # Operaciones Integradas sólo puede escalar a Strategic.
    if current_kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        return ToolConfigurationKind.STRATEGIC
    # Strategic es terminal: no admite ningún destino adicional.
    return None
