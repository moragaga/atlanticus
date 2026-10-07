"""
Política de dirección válida para escalamiento de alarmas.

La secuencia permitida avanza desde Process a Integrated Operations y luego a Strategic.
Esta regla se aloja aquí para no depender del dominio de Command Center.
"""
from __future__ import annotations

from ada.contracts.tools.enums import ToolConfigurationKind


def next_routing_tool_kind(current_kind: ToolConfigurationKind) -> ToolConfigurationKind | None:
    if not isinstance(current_kind, ToolConfigurationKind):
        raise TypeError('current_kind must be a ToolConfigurationKind')
    if current_kind is ToolConfigurationKind.PROCESS:
        return ToolConfigurationKind.INTEGRATED_OPERATIONS
    if current_kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        return ToolConfigurationKind.STRATEGIC
    return None
