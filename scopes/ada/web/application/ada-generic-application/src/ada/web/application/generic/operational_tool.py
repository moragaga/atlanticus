from __future__ import annotations

from ada.web.tools.configuration import ToolConfiguration, create_tool_projection_service
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore

DEFAULT_OPERATIONAL_TOOL_SOURCE_KEY = SourceKey('tools')


class _StartupToolProjectionStore(ProjectionStore[ToolConfiguration]):
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[ToolConfiguration]] = {}

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[ToolConfiguration] | None:
        return self._active.get(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[ToolConfiguration],
    ) -> ProjectionRecord[ToolConfiguration]:
        self._active[projection.source_key] = projection
        return projection


def resolve_current_tool_projection(
    *,
    source: SourceStore,
    source_key: SourceKey = DEFAULT_OPERATIONAL_TOOL_SOURCE_KEY,
) -> ProjectionRecord[ToolConfiguration]:
    if not isinstance(source, SourceStore):
        raise TypeError('source must be a SourceStore')
    if not isinstance(source_key, SourceKey):
        raise TypeError('source_key must be a SourceKey')
    service = create_tool_projection_service(
        source=source,
        projection=_StartupToolProjectionStore(),
    )
    target = service.select_current_target(source_key)
    if target is None:
        raise RuntimeError('Operational Tool source has no current release')
    return service.project(target).projection
