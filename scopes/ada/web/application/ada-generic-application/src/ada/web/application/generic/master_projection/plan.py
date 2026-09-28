from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseRef
from atlanticus.web.source.store import SourceStore


class ProjectionPlanState(StrEnum):
    SOURCE_MISSING = 'SOURCE_MISSING'
    CURRENT = 'CURRENT'
    NEVER_PROJECTED = 'NEVER_PROJECTED'
    OUTDATED = 'OUTDATED'
    BLOCKED = 'BLOCKED'
    UNAVAILABLE = 'UNAVAILABLE'


class UsersPlanState(StrEnum):
    CATALOG_UNAVAILABLE = 'CATALOG_UNAVAILABLE'
    SNAPSHOT_MISSING = 'SNAPSHOT_MISSING'
    PROFILES_PENDING = 'PROFILES_PENDING'
    SNAPSHOT_SELECTION_REQUIRED = 'SNAPSHOT_SELECTION_REQUIRED'


@dataclass(frozen=True, slots=True)
class ProjectionDomain:
    key: SourceKey
    source: SourceStore
    projection: ProjectionStore[Any]
    service: SourceProjectionService[Any]
    requires: tuple[SourceKey, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.key, SourceKey):
            raise TypeError('Projection domain key is invalid')
        required = tuple(self.requires)
        if any(not isinstance(key, SourceKey) for key in required):
            raise TypeError('Projection domain prerequisites are invalid')
        if self.key in required or len(set(required)) != len(required):
            raise ValueError('Projection domain prerequisites must be unique and external')
        object.__setattr__(self, 'requires', required)


@dataclass(frozen=True, slots=True)
class ProjectionPlanEntry:
    key: SourceKey
    state: ProjectionPlanState
    source_release: SourceReleaseRef | None
    current_target: ProjectionTarget | None
    projected_target: ProjectionTarget | None
    prerequisites: tuple[SourceKey, ...]
    blocked_by: tuple[SourceKey, ...] = ()
    error_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            'source_key': self.key.value,
            'state': self.state.value,
            'source_release': _release_dict(self.source_release),
            'current_target': _target_dict(self.current_target),
            'projected_target': _target_dict(self.projected_target),
            'prerequisites': [key.value for key in self.prerequisites],
            'blocked_by': [key.value for key in self.blocked_by],
            'error_type': self.error_type,
        }


@dataclass(frozen=True, slots=True)
class UsersPlan:
    state: UsersPlanState
    snapshot_ids: tuple[str, ...] = ()
    error_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            'state': self.state.value,
            'snapshot_ids': list(self.snapshot_ids),
            'error_type': self.error_type,
            'operation': 'users.replace',
            'executable': False,
        }


@dataclass(frozen=True, slots=True)
class MasterProjectionPlan:
    entries: tuple[ProjectionPlanEntry, ...]
    users: UsersPlan

    @property
    def ready(self) -> tuple[ProjectionPlanEntry, ...]:
        return tuple(
            entry for entry in self.entries
            if entry.state in (ProjectionPlanState.NEVER_PROJECTED, ProjectionPlanState.OUTDATED)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            'mode': 'READ_ONLY',
            'entries': [entry.to_dict() for entry in self.entries],
            'ready_source_keys': [entry.key.value for entry in self.ready],
            'users': self.users.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _Observed:
    source_release: SourceReleaseRef | None
    projected_target: ProjectionTarget | None
    error_type: str | None = None


class MasterProjectionPlanner:
    def __init__(
        self,
        *,
        domains: tuple[ProjectionDomain, ...],
        profiles_key: SourceKey,
        users_snapshot_ids: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        domains = tuple(domains)
        if not domains:
            raise ValueError('Master Projection requires projection domains')
        if len({domain.key for domain in domains}) != len(domains):
            raise ValueError('Master Projection domain keys must be unique')
        if profiles_key not in {domain.key for domain in domains}:
            raise ValueError('Master Projection requires the Profiles domain')
        if users_snapshot_ids is not None and not callable(users_snapshot_ids):
            raise TypeError('Users snapshot catalog must be callable')
        self._domains = {domain.key: domain for domain in domains}
        self._order = _dependency_order(self._domains)
        self._profiles_key = profiles_key
        self._users_snapshot_ids = users_snapshot_ids

    def inspect(self) -> MasterProjectionPlan:
        observed = {key: self._observe(self._domains[key]) for key in self._order}
        planned: dict[SourceKey, ProjectionPlanEntry] = {}
        for key in self._order:
            domain = self._domains[key]
            state = observed[key]
            projected_target = state.projected_target
            common = dict(
                key=key,
                source_release=state.source_release,
                projected_target=projected_target,
                prerequisites=domain.requires,
            )
            if state.error_type is not None:
                entry = ProjectionPlanEntry(
                    state=ProjectionPlanState.UNAVAILABLE,
                    current_target=None,
                    error_type=state.error_type,
                    **common,
                )
            elif state.source_release is None:
                entry = ProjectionPlanEntry(
                    state=ProjectionPlanState.SOURCE_MISSING,
                    current_target=None,
                    **common,
                )
            else:
                blockers = tuple(
                    required for required in domain.requires
                    if planned[required].state is not ProjectionPlanState.CURRENT
                )
                if blockers:
                    entry = ProjectionPlanEntry(
                        state=ProjectionPlanState.BLOCKED,
                        current_target=None,
                        blocked_by=blockers,
                        **common,
                    )
                else:
                    entry = self._resolve(domain, state, projected_target, planned)
            planned[key] = entry
        return MasterProjectionPlan(
            entries=tuple(planned[key] for key in self._order),
            users=self._inspect_users(planned[self._profiles_key]),
        )

    @staticmethod
    def _observe(domain: ProjectionDomain) -> _Observed:
        try:
            snapshot = domain.source.get_current(domain.key)
            if snapshot.source_key != domain.key:
                raise ValueError('Source snapshot key does not match projection domain')
            active = domain.projection.get_active(domain.key)
            if active is not None and active.source_key != domain.key:
                raise ValueError('Projection record key does not match projection domain')
            release = snapshot.current.release_ref if snapshot.current is not None else None
            return _Observed(
                source_release=release,
                projected_target=active.target if active is not None else None,
            )
        except Exception as error:
            return _Observed(
                source_release=None, projected_target=None, error_type=type(error).__name__
            )

    @staticmethod
    def _resolve(
        domain: ProjectionDomain,
        observed: _Observed,
        projected_target: ProjectionTarget | None,
        planned: dict[SourceKey, ProjectionPlanEntry],
    ) -> ProjectionPlanEntry:
        common = dict(
            key=domain.key,
            source_release=observed.source_release,
            projected_target=projected_target,
            prerequisites=domain.requires,
        )
        try:
            target = domain.service.select_current_target(domain.key)
            expected = tuple(planned[key].current_target for key in domain.requires)
            if (
                target is None
                or target.source_key != domain.key
                or target.source_release != observed.source_release
                or target.dependencies != tuple(
                    sorted(expected, key=lambda item: item.source_key.value)
                )
            ):
                return ProjectionPlanEntry(
                    state=ProjectionPlanState.UNAVAILABLE,
                    current_target=None,
                    error_type='TARGET_CHANGED_OR_INCOMPATIBLE',
                    **common,
                )
        except Exception as error:
            return ProjectionPlanEntry(
                state=ProjectionPlanState.UNAVAILABLE,
                current_target=None,
                error_type=type(error).__name__,
                **common,
            )
        state = (
            ProjectionPlanState.CURRENT if projected_target == target
            else ProjectionPlanState.NEVER_PROJECTED if projected_target is None
            else ProjectionPlanState.OUTDATED
        )
        return ProjectionPlanEntry(state=state, current_target=target, **common)

    def _inspect_users(self, profiles: ProjectionPlanEntry) -> UsersPlan:
        if self._users_snapshot_ids is None:
            return UsersPlan(state=UsersPlanState.CATALOG_UNAVAILABLE)
        try:
            identifiers = self._users_snapshot_ids()
            if (
                not isinstance(identifiers, tuple)
                or any(
                    not isinstance(value, str) or not value.strip() or value != value.strip()
                    for value in identifiers
                )
                or len(identifiers) != len(set(identifiers))
            ):
                raise ValueError('Users snapshot catalog returned invalid identifiers')
            snapshot_ids = tuple(sorted(identifiers))
        except Exception as error:
            return UsersPlan(
                state=UsersPlanState.CATALOG_UNAVAILABLE,
                error_type=type(error).__name__,
            )
        if not snapshot_ids:
            state = UsersPlanState.SNAPSHOT_MISSING
        elif profiles.state is not ProjectionPlanState.CURRENT:
            state = UsersPlanState.PROFILES_PENDING
        else:
            state = UsersPlanState.SNAPSHOT_SELECTION_REQUIRED
        return UsersPlan(state=state, snapshot_ids=snapshot_ids)


def _dependency_order(domains: dict[SourceKey, ProjectionDomain]) -> tuple[SourceKey, ...]:
    ordered: list[SourceKey] = []
    visiting: set[SourceKey] = set()
    visited: set[SourceKey] = set()

    def visit(key: SourceKey) -> None:
        if key in visiting:
            raise ValueError('Master Projection domains contain a dependency cycle')
        if key in visited:
            return
        visiting.add(key)
        for required in sorted(domains[key].requires, key=lambda item: item.value):
            if required not in domains:
                raise ValueError('Master Projection domain prerequisite is not registered')
            visit(required)
        visiting.remove(key)
        visited.add(key)
        ordered.append(key)

    for key in sorted(domains, key=lambda item: item.value):
        visit(key)
    return tuple(ordered)


def _release_dict(release: SourceReleaseRef | None) -> dict[str, str] | None:
    if release is None:
        return None
    return {
        'release_id': release.release_id.value,
        'published_at_utc': release.published_at_utc.isoformat(),
    }


def _target_dict(target: ProjectionTarget | None) -> dict[str, object] | None:
    if target is None:
        return None
    return {
        'source_key': target.source_key.value,
        'source_release': _release_dict(target.source_release),
        'dependencies': [_target_dict(dependency) for dependency in target.dependencies],
    }
