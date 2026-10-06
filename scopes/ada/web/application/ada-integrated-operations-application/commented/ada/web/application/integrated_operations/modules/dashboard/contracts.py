from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.enums import ToolScope


# Toda card visible debe quedar enlazada a una identidad real de subcomponente definida por desarrollo.
@dataclass(frozen=True, slots=True)
class DashboardCardBinding:
    key: str
    label: str
    tool_subcomponent_key: str


# El componente conserva una key visual independiente, pero exige la identidad Tool usada por runtime.
@dataclass(frozen=True, slots=True)
class DashboardComponentBinding:
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str
    cards: tuple[DashboardCardBinding, ...]


# La card compartida exige owner, subcomponent y vínculos explícitos; no deriva identidades desde labels.
@dataclass(frozen=True, slots=True)
class DashboardSharedCardBinding:
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str
    tool_subcomponent_key: str
    linked_tool_component_keys: tuple[str, ...] = ()
