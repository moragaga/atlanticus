from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.profiles import (
    NavigationProfileOptionsProvider,
    profile_options,
)
from atlanticus.web.navigation.configuration.source_release import NavigationSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore

NavigationProjectionIssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class NavigationProjectionIssue:
    code: str
    message: str
    level: NavigationProjectionIssueLevel = 'error'
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise NavigationConfigurationProjectionError(
                'Navigation projection issue code must not be empty'
            )
        if not self.message.strip():
            raise NavigationConfigurationProjectionError(
                'Navigation projection issue message must not be empty'
            )
        if self.level not in {'error', 'warning'}:
            raise NavigationConfigurationProjectionError(
                'Navigation projection issue level is invalid'
            )


NavigationProjectionValidator = Callable[
    [NavigationConfigurationCatalog],
    tuple[NavigationProjectionIssue, ...],
]


def create_navigation_profile_options_validator(
    profile_options_provider: NavigationProfileOptionsProvider,
) -> NavigationProjectionValidator:
    def validate(
        catalog: NavigationConfigurationCatalog,
    ) -> tuple[NavigationProjectionIssue, ...]:
        known = {option.key for option in profile_options(profile_options_provider)}
        return tuple(
            NavigationProjectionIssue(
                code='navigation.profile.unknown',
                message=f'Unknown navigation profile {profile_key!r}',
            )
            for profile_key in catalog.configured_profiles()
            if profile_key not in known
        )

    return validate


class NavigationProjectionBuilder(ProjectionBuilder[NavigationConfigurationCatalog]):
    def __init__(
        self,
        *,
        codec: NavigationSourceCodec | None = None,
        validators: tuple[NavigationProjectionValidator, ...] = (),
    ) -> None:
        self._codec = codec or NavigationSourceCodec()
        self._validators = validators

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> NavigationConfigurationCatalog:
        del target, release
        catalog = self._codec.decode(resources).catalog
        catalog.to_definition()
        issues = tuple(issue for validator in self._validators for issue in validator(catalog))
        if any(issue.level == 'error' for issue in issues):
            raise NavigationConfigurationProjectionError(
                'Published navigation configuration is not valid for projection'
            )
        return catalog


def create_navigation_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[NavigationConfigurationCatalog],
    validators: tuple[NavigationProjectionValidator, ...] = (),
) -> SourceProjectionService[NavigationConfigurationCatalog]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=NavigationProjectionBuilder(validators=validators),
    )
