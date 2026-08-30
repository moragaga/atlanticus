from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from ada.web.content_state.core import (
    ContentState,
    SourceFreshnessCondition,
    resolve_content_state_from_freshness,
)

from .errors import ContentStateDependencyError, MissingSourceFreshnessError
from .models import ContentStateDependency, require_component_key, require_source_key


class ContentStateDependencyGraph:
    def __init__(self, dependencies: Iterable[ContentStateDependency] = ()) -> None:
        normalized = tuple(dependencies)
        by_component: dict[str, ContentStateDependency] = {}
        by_source: dict[str, list[str]] = {}

        for dependency in normalized:
            if not isinstance(dependency, ContentStateDependency):
                raise TypeError('Dependency graph requires ContentStateDependency values')
            if dependency.component_key in by_component:
                raise ContentStateDependencyError(
                    f'Duplicate Content State component dependency: {dependency.component_key!r}'
                )
            by_component[dependency.component_key] = dependency
            for source_key in dependency.source_keys:
                by_source.setdefault(source_key, []).append(dependency.component_key)

        self._dependencies = normalized
        self._by_component = MappingProxyType(by_component)
        self._by_source = MappingProxyType(
            {source_key: tuple(component_keys) for source_key, component_keys in by_source.items()}
        )

    @property
    def dependencies(self) -> tuple[ContentStateDependency, ...]:
        return self._dependencies

    def components_for_source(self, source_key: str) -> tuple[str, ...]:
        require_source_key(source_key)
        return self._by_source.get(source_key, ())

    def sources_for_component(self, component_key: str) -> tuple[str, ...]:
        require_component_key(component_key)
        dependency = self._by_component.get(component_key)
        if dependency is None:
            return ()
        return dependency.source_keys

    def resolve(
        self,
        source_conditions: Mapping[str, SourceFreshnessCondition],
    ) -> Mapping[str, ContentState]:
        _validate_source_conditions(source_conditions)
        resolved: dict[str, ContentState] = {}
        for dependency in self._dependencies:
            conditions: list[SourceFreshnessCondition] = []
            for source_key in dependency.source_keys:
                condition = source_conditions.get(source_key)
                if condition is None:
                    raise MissingSourceFreshnessError(
                        f'Missing freshness condition for required source: {source_key!r}'
                    )
                conditions.append(condition)
            resolved[dependency.component_key] = resolve_content_state_from_freshness(*conditions)
        return MappingProxyType(resolved)


def _validate_source_conditions(
    source_conditions: Mapping[str, SourceFreshnessCondition],
) -> None:
    if not isinstance(source_conditions, Mapping):
        raise TypeError('Source freshness conditions must be a mapping')
    for source_key, condition in source_conditions.items():
        require_source_key(source_key)
        if not isinstance(condition, SourceFreshnessCondition):
            raise TypeError('Source freshness mapping requires SourceFreshnessCondition values')
