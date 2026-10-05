from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.enums import ToolScope
from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)

DASHBOARD_CONTEXT_SERVICE_KEY = 'ada.integrated_operations.dashboard.context'


@dataclass(frozen=True, slots=True)
class DashboardContext:
    binding: OperationalRenderBinding | None

    def components_for_scope(
        self,
        scope: ToolScope,
    ) -> tuple[OperationalComponentBinding, ...]:
        if not isinstance(scope, ToolScope):
            raise TypeError('scope must be ToolScope')
        if self.binding is None:
            return ()
        return tuple(
            component
            for component in self.binding.components
            if component.component.scope is scope
        )
