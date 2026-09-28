from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.web.application.generic.master_projection.apply import (
    MasterApplyError,
    MasterApplyOutcome,
    MasterProjectionExecutor,
)
from ada.web.application.generic.master_projection.plan import (
    MasterProjectionPlanner,
    ProjectionDomain,
    ProjectionPlanState,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def key(value: str) -> SourceKey:
    return SourceKey(value)


def release(value: str) -> SourceReleaseRef:
    return SourceReleaseRef(SourceReleaseId(value), NOW)


class Sources:
    def __init__(self) -> None:
        self.current = {}

    def get_current(self, source_key):
        current = self.current.get(source_key)
        return SourceSnapshot(
            source_key=source_key,
            current=(
                SourceReleaseSummary(current, Digest('sha256', 'current'))
                if current is not None else None
            ),
            concurrency_token=ConcurrencyToken('current') if current is not None else None,
        )


class Projections:
    def __init__(self) -> None:
        self.active = {}

    def get_active(self, source_key):
        return self.active.get(source_key)


class Projector:
    def __init__(self, source, projection, required=()) -> None:
        self.source = source
        self.projection = projection
        self.required = required
        self.calls = []
        self.fail = False
        self.skip_persistence = False

    def select_current_target(self, source_key):
        snapshot = self.source.get_current(source_key)
        if snapshot.current is None:
            return None
        dependencies = tuple(
            self.projection.get_active(required).target for required in self.required
        )
        return ProjectionTarget(source_key, snapshot.current.release_ref, dependencies)

    def project(self, target):
        self.calls.append(target)
        if self.fail:
            raise RuntimeError('Private provider failure')
        record = ProjectionRecord(
            source_key=target.source_key,
            source_release_id=target.source_release_id,
            source_published_at_utc=target.source_release.published_at_utc,
            projected_at_utc=NOW,
            payload=object(),
            dependencies=target.dependencies,
        )
        if not self.skip_persistence:
            self.projection.active[target.source_key] = record
        return SimpleNamespace(target=target, projection=record)


@pytest.fixture
def backend():
    sources = Sources()
    projections = Projections()
    specs = {
        'profiles-configuration': (),
        'ada-access': ('profiles-configuration',),
        'navigation': (),
    }
    services = {}
    domains = []
    for name, required in specs.items():
        service = Projector(sources, projections, tuple(key(item) for item in required))
        services[name] = service
        domains.append(ProjectionDomain(
            key=key(name),
            source=sources,
            projection=projections,
            service=service,
            requires=tuple(key(item) for item in required),
        ))
    planner = MasterProjectionPlanner(
        domains=tuple(domains),
        profiles_key=key('profiles-configuration'),
    )
    executor = MasterProjectionExecutor(planner=planner, domains=tuple(domains))
    return sources, projections, services, planner, executor


def entry(planner, name):
    return next(item for item in planner.inspect().entries if item.key == key(name))


def test_applies_one_selected_domain_and_preserves_independent_pending_work(backend):
    sources, projections, services, planner, executor = backend
    for name in services:
        sources.current[key(name)] = release(f'{name}-1')
    profiles = entry(planner, 'profiles-configuration')
    assert entry(planner, 'ada-access').state is ProjectionPlanState.BLOCKED
    result = executor.apply(source_key=profiles.key, expected_target=profiles.current_target)
    assert result.outcome is MasterApplyOutcome.APPLIED
    assert len(services['profiles-configuration'].calls) == 1
    assert not services['navigation'].calls
    assert not services['ada-access'].calls
    assert key('navigation') not in projections.active
    access = entry(planner, 'ada-access')
    assert access.state is ProjectionPlanState.NEVER_PROJECTED
    assert access.current_target.dependencies == (result.target,)
    executor.apply(source_key=access.key, expected_target=access.current_target)
    assert len(services['ada-access'].calls) == 1
    assert entry(planner, 'navigation').state is ProjectionPlanState.NEVER_PROJECTED


def test_repeating_an_exact_current_target_does_not_write_again(backend):
    sources, _projections, services, planner, executor = backend
    sources.current[key('profiles-configuration')] = release('profiles-1')
    selected = entry(planner, 'profiles-configuration')
    executor.apply(source_key=selected.key, expected_target=selected.current_target)
    repeated = executor.apply(source_key=selected.key, expected_target=selected.current_target)
    assert repeated.outcome is MasterApplyOutcome.ALREADY_CURRENT
    assert len(services['profiles-configuration'].calls) == 1


def test_stale_selection_cannot_deploy_earlier_source_version(backend):
    sources, _projections, services, planner, executor = backend
    source_key = key('profiles-configuration')
    sources.current[source_key] = release('profiles-1')
    old = entry(planner, 'profiles-configuration')
    sources.current[source_key] = release('profiles-2')
    with pytest.raises(MasterApplyError) as raised:
        executor.apply(source_key=source_key, expected_target=old.current_target)
    assert raised.value.reason == 'STALE_SELECTION'
    assert not services['profiles-configuration'].calls


def test_missing_and_blocked_sources_do_not_execute(backend):
    sources, _projections, services, _planner, executor = backend
    source_key = key('profiles-configuration')
    expected = ProjectionTarget(source_key, release('profiles-1'))
    with pytest.raises(MasterApplyError) as missing:
        executor.apply(source_key=source_key, expected_target=expected)
    assert missing.value.reason == 'SOURCE_MISSING'
    sources.current[key('ada-access')] = release('access-1')
    with pytest.raises(MasterApplyError) as blocked:
        executor.apply(
            source_key=key('ada-access'),
            expected_target=ProjectionTarget(key('ada-access'), release('access-1')),
        )
    assert blocked.value.reason == 'BLOCKED'
    assert not any(service.calls for service in services.values())


def test_rejects_unknown_domain_and_cross_domain_target(backend):
    _sources, _projections, _services, _planner, executor = backend
    with pytest.raises(MasterApplyError) as unknown:
        executor.apply(
            source_key=key('users'),
            expected_target=ProjectionTarget(key('users'), release('users-1')),
        )
    assert unknown.value.reason == 'INVALID_SELECTION'
    with pytest.raises(MasterApplyError) as mismatch:
        executor.apply(
            source_key=key('navigation'),
            expected_target=ProjectionTarget(key('profiles-configuration'), release('p-1')),
        )
    assert mismatch.value.reason == 'INVALID_SELECTION'


def test_execution_error_never_claims_success(backend):
    sources, projections, services, planner, executor = backend
    source_key = key('profiles-configuration')
    sources.current[source_key] = release('profiles-1')
    selected = entry(planner, 'profiles-configuration')
    services['profiles-configuration'].fail = True
    with pytest.raises(MasterApplyError) as raised:
        executor.apply(source_key=source_key, expected_target=selected.current_target)
    assert raised.value.reason == 'EXECUTION_FAILED'
    assert projections.get_active(source_key) is None


def test_success_response_without_persistence_fails_verification(backend):
    sources, _projections, services, planner, executor = backend
    source_key = key('profiles-configuration')
    sources.current[source_key] = release('profiles-1')
    selected = entry(planner, 'profiles-configuration')
    services['profiles-configuration'].skip_persistence = True
    with pytest.raises(MasterApplyError) as raised:
        executor.apply(source_key=source_key, expected_target=selected.current_target)
    assert raised.value.reason == 'VERIFICATION_FAILED'
