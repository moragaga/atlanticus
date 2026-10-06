from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.enums import ToolScope


# Contrato visual mínimo compartido por las composiciones Mine y Plant.
@dataclass(frozen=True, slots=True)
class DashboardCardBinding:
    key: str
    label: str
    tool_subcomponent_key: str | None = None


# Un componente visual conserva su scope y puede recibir después la identidad Tool definida por desarrollo.
@dataclass(frozen=True, slots=True)
class DashboardComponentBinding:
    key: str
    label: str
    scope: ToolScope
    cards: tuple[DashboardCardBinding, ...]
    tool_component_key: str | None = None


# Una card compartida conserva owner, subcomponent y vínculos sin imponer semántica de un scope concreto.
@dataclass(frozen=True, slots=True)
class DashboardSharedCardBinding:
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str | None = None
    tool_subcomponent_key: str | None = None
    linked_tool_component_keys: tuple[str, ...] = ()
