from typing import cast

import pytest

from atlanticus.web.users.configuration import (
    UsersRuntimeMaterializingProjectionRepository,
)
from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
from atlanticus.web.users.configuration.projection import UsersProjectionState


class RecordingRuntimeProjectionWriter:
    def __init__(
        self,
        *,
        events: list[tuple[str, object, str]],
        healthy: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.events = events
        self.healthy = healthy
        self.error = error
        self.health_calls = 0

    def materialize(self, bundle: UsersConfigurationBundle, *, actor: str) -> None:
        self.events.append(('runtime', bundle, actor))
        if self.error is not None:
            raise self.error

    def health_check(self) -> bool:
        self.health_calls += 1
        return self.healthy


class RecordingProjectionRepository:
    def __init__(
        self,
        *,
        state: UsersProjectionState | None,
        events: list[tuple[str, object, str]],
        healthy: bool = True,
    ) -> None:
        self.state = state
        self.events = events
        self.healthy = healthy
        self.health_calls = 0

    def load_state(self) -> UsersProjectionState | None:
        return self.state

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState:
        self.events.append(('projection', bundle, actor))
        if self.state is None:
            raise AssertionError('projection state was not configured')
        return self.state

    def health_check(self) -> bool:
        self.health_calls += 1
        return self.healthy


def test_runtime_materialization_happens_before_projection_commit() -> None:
    events: list[tuple[str, object, str]] = []
    bundle = cast(UsersConfigurationBundle, object())
    state = cast(UsersProjectionState, object())
    runtime = RecordingRuntimeProjectionWriter(events=events)
    projection = RecordingProjectionRepository(state=state, events=events)
    repository = UsersRuntimeMaterializingProjectionRepository(
        runtime=runtime,
        projection=projection,
    )

    result = repository.project(bundle, actor='operator@example.com')

    assert result is state
    assert events == [
        ('runtime', bundle, 'operator@example.com'),
        ('projection', bundle, 'operator@example.com'),
    ]


def test_projection_commit_is_not_attempted_when_runtime_materialization_fails() -> None:
    events: list[tuple[str, object, str]] = []
    bundle = cast(UsersConfigurationBundle, object())
    runtime = RecordingRuntimeProjectionWriter(
        events=events,
        error=RuntimeError('runtime unavailable'),
    )
    projection = RecordingProjectionRepository(
        state=cast(UsersProjectionState, object()),
        events=events,
    )
    repository = UsersRuntimeMaterializingProjectionRepository(
        runtime=runtime,
        projection=projection,
    )

    with pytest.raises(RuntimeError, match='runtime unavailable'):
        repository.project(bundle, actor='operator@example.com')

    assert events == [('runtime', bundle, 'operator@example.com')]


def test_projection_state_is_owned_by_the_existing_projection_repository() -> None:
    events: list[tuple[str, object, str]] = []
    state = cast(UsersProjectionState, object())
    repository = UsersRuntimeMaterializingProjectionRepository(
        runtime=RecordingRuntimeProjectionWriter(events=events),
        projection=RecordingProjectionRepository(state=state, events=events),
    )

    assert repository.load_state() is state


def test_health_check_requires_runtime_and_projection_and_checks_both() -> None:
    events: list[tuple[str, object, str]] = []
    runtime = RecordingRuntimeProjectionWriter(events=events, healthy=False)
    projection = RecordingProjectionRepository(state=None, events=events, healthy=True)
    repository = UsersRuntimeMaterializingProjectionRepository(
        runtime=runtime,
        projection=projection,
    )

    assert repository.health_check() is False
    assert runtime.health_calls == 1
    assert projection.health_calls == 1
