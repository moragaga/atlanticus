from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .errors import ContentStateDependencyError, MissingSourceFreshnessError
from .freshness import SourceFreshnessCondition, resolve_content_state_from_freshness
from .models import ContentState

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


@dataclass(frozen=True, slots=True)
class ContentStateDependency:
    component_key: str
    source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_key(self.component_key, label='component key')
        normalized = tuple(self.source_keys)
        if not normalized:
            raise ContentStateDependencyError('Content State dependency requires source_keys')
        if len(set(normalized)) != len(normalized):
            raise ContentStateDependencyError('Content State dependency source_keys must be unique')
        for source_key in normalized:
            require_source_key(source_key)
        object.__setattr__(self, 'source_keys', normalized)


def require_source_key(source_key: str) -> str:
    _require_key(source_key, label='source key')
    return source_key


def require_component_key(component_key: str) -> str:
    _require_key(component_key, label='component key')
    return component_key


def _require_key(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _KEY_PATTERN.fullmatch(value):
        raise ContentStateDependencyError(f'Invalid Content State {label}: {value!r}')




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
