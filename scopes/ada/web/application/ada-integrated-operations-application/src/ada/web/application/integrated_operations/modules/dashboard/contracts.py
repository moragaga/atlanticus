from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.contracts.tools.enums import ToolScope
from ada.web.content_state import ContentState

class OperationalControlSource(StrEnum):
    PI = 'pi'
    DISPATCH = 'dispatch'


def require_dashboard_source_keys(
    value: tuple[OperationalControlSource, ...] | None,
) -> tuple[OperationalControlSource, ...] | None:
    if value is None:
        return None
    if not isinstance(value, tuple):
        raise TypeError('Dashboard source_keys must be a tuple or None')
    if len(value) != len(set(value)):
        raise ValueError('Dashboard source_keys must be unique')
    if any(not isinstance(key, OperationalControlSource) for key in value):
        raise TypeError('Dashboard source_keys must contain OperationalControlSource values')
    return value


@dataclass(frozen=True, slots=True)
class DashboardCardBinding:
    key: str
    label: str
    tool_subcomponent_key: str
    content_state: ContentState = ContentState.READY
    source_keys: tuple[OperationalControlSource, ...] | None = None

    def __post_init__(self) -> None:
        require_dashboard_source_keys(self.source_keys)


@dataclass(frozen=True, slots=True)
class DashboardComponentBinding:
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str
    cards: tuple[DashboardCardBinding, ...]


@dataclass(frozen=True, slots=True)
class DashboardSharedCardBinding:
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str
    tool_subcomponent_key: str
    linked_tool_component_keys: tuple[str, ...] = ()
    source_keys: tuple[OperationalControlSource, ...] | None = None

    def __post_init__(self) -> None:
        require_dashboard_source_keys(self.source_keys)
