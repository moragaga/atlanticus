from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.enums import ToolScope
from ada.contracts.tools.validation import require_key
from ada.web.content_state import ContentState
from ada.web.ui.global_indicator import GlobalIndicatorDefinition


@dataclass(frozen=True, slots=True)
class DashboardGlobalIndicatorBinding:
    definition: GlobalIndicatorDefinition
    scopes: tuple[ToolScope, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.definition, GlobalIndicatorDefinition):
            raise TypeError('definition must be GlobalIndicatorDefinition')
        if not isinstance(self.scopes, tuple):
            raise TypeError('Global Indicator scopes must be a tuple')
        if not self.scopes:
            raise ValueError('Global Indicator requires at least one presentation scope')
        if any(not isinstance(scope, ToolScope) for scope in self.scopes):
            raise TypeError('Global Indicator scopes must contain ToolScope values')
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError('Global Indicator presentation scopes must be unique')

    def appears_in(self, scope: ToolScope) -> bool:
        if not isinstance(scope, ToolScope):
            raise TypeError('scope must be ToolScope')
        return scope in self.scopes


@dataclass(frozen=True, slots=True)
class DashboardGlobalIndicatorsRuntimeBinding:
    tool_key: str
    indicators: tuple[DashboardGlobalIndicatorBinding, ...]
    content_state: ContentState = ContentState.READY

    def __post_init__(self) -> None:
        object.__setattr__(self, 'tool_key', require_key(self.tool_key, label='Tool key'))
        if not isinstance(self.indicators, tuple):
            raise TypeError('Global Indicator bindings must be a tuple')
        if not self.indicators:
            raise ValueError('Global Indicators runtime requires at least one indicator')
        if any(not isinstance(item, DashboardGlobalIndicatorBinding) for item in self.indicators):
            raise TypeError(
                'Global Indicator bindings must contain DashboardGlobalIndicatorBinding values'
            )
        if not isinstance(self.content_state, ContentState):
            raise TypeError('Global Indicators runtime content_state must be ContentState')
        keys = tuple(item.definition.key for item in self.indicators)
        if len(keys) != len(set(keys)):
            raise ValueError('Global Indicator bindings must have unique indicator keys')
