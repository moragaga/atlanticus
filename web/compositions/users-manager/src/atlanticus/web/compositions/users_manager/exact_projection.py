from __future__ import annotations

from atlanticus.web.projection.models import (
    ProjectionExecutionResult,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError
from atlanticus.web.users.configuration.source_projection import create_users_projection_service


class UsersManagerExactProjectionWorkflow:
    def __init__(
        self,
        *,
        projection: SourceProjectionService[UsersProfilesConfiguration],
        source_key: SourceKey,
    ) -> None:
        self._projection = projection
        self._source_key = source_key

    def get_status(self) -> ProjectionStatus:
        return self._projection.get_status(self._source_key)

    def get_current_projection_target(self) -> ProjectionTarget | None:
        return self._projection.select_current_target(self._source_key)

    def project(
        self,
        target: ProjectionTarget,
    ) -> ProjectionExecutionResult[UsersProfilesConfiguration]:
        if target.source_key != self._source_key:
            raise UsersConfigurationProjectionError(
                'Users projection target uses a different source key'
            )
        return self._projection.project(target)


def create_users_manager_exact_projection_workflow(
    *,
    source: SourceStore,
    projection: ProjectionStore[UsersProfilesConfiguration],
    source_key: SourceKey,
) -> UsersManagerExactProjectionWorkflow:
    return UsersManagerExactProjectionWorkflow(
        projection=create_users_projection_service(
            source=source,
            projection=projection,
        ),
        source_key=source_key,
    )
