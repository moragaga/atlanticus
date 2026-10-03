from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from atlanticus.web.master_projection.plan import (
    MasterProjectionPlanner,
    ProjectionDomain,
    ProjectionPlanState,
    UsersPlanState,
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


def key(name):
    return SourceKey(name)


def release(name):
    return SourceReleaseRef(SourceReleaseId(name), NOW)


class Sources:
    def __init__(self):
        self.releases = {}
        self.failed = set()
        self.after_read = {}

    def get_current(self, source_key):
        if source_key in self.failed:
            raise ConnectionError('private source connection details')
        current = self.releases.get(source_key)
        if source_key in self.after_read:
            self.releases[source_key] = self.after_read.pop(source_key)
        return SourceSnapshot(
            source_key=source_key,
            current=(
                SourceReleaseSummary(release_ref=current, content_hash=Digest('sha256', 'f'))
                if current is not None
                else None
            ),
            concurrency_token=ConcurrencyToken('etag') if current is not None else None,
        )


class Projections:
    def __init__(self):
        self.active = {}
        self.failed = set()

    def get_active(self, source_key):
        if source_key in self.failed:
            raise ConnectionError('private projection connection details')
        return self.active.get(source_key)


class Selector:
    def __init__(self, source, projection, dependencies=()):
        self.source = source
        self.projection = projection
        self.dependencies = dependencies
        self.override = None

    def select_current_target(self, source_key):
        if self.override is not None:
            return self.override
        snapshot = self.source.get_current(source_key)
        if snapshot.current is None:
            return None
        dependencies = tuple(
            self.projection.get_active(required).target for required in self.dependencies
        )
        return ProjectionTarget(
            source_key=source_key,
            source_release=snapshot.current.release_ref,
            dependencies=dependencies,
        )


def projected(target):
    return ProjectionRecord(
        source_key=target.source_key,
        source_release_id=target.source_release_id,
        source_published_at_utc=target.source_release.published_at_utc,
        projected_at_utc=NOW,
        payload=object(),
        dependencies=target.dependencies,
    )


def setup(snapshots=None):
    requirements = {
        'profiles': (),
        'access': ('profiles',),
        'navigation': (),
        'tools': (),
        'registry': ('tools',),
        'definitions': ('registry',),
    }
    sources = Sources()
    projections = Projections()
    selectors = {}
    entries = []
    for name, prerequisite_names in reversed(tuple(requirements.items())):
        required = tuple(key(value) for value in prerequisite_names)
        selector = Selector(sources, projections, required)
        selectors[name] = selector
        entries.append(
            ProjectionDomain(
                key=key(name),
                source=sources,
                projection=projections,
                service=selector,
                requires=required,
            )
        )
    planner = MasterProjectionPlanner(
        domains=tuple(entries),
        profiles_key=key('profiles'),
        users_snapshot_ids=snapshots,
    )
    return planner, sources, projections, selectors


def publish(sources, *names):
    for name in names:
        sources.releases[key(name)] = release(f'{name}-r1')


def activate(sources, projections, name, *dependencies):
    target = ProjectionTarget(
        key(name),
        sources.releases[key(name)],
        tuple(projections.active[key(item)].target for item in dependencies),
    )
    projections.active[key(name)] = projected(target)


def by_name(plan):
    return {entry.key.value: entry for entry in plan.entries}


def test_empty_environment_reports_missing_sources_and_no_users_snapshot():
    planner, sources, projections, _ = setup(snapshots=lambda: ())
    plan = planner.inspect()
    assert len(plan.entries) == 6
    assert {entry.state for entry in plan.entries} == {ProjectionPlanState.SOURCE_MISSING}
    assert plan.users.state is UsersPlanState.SNAPSHOT_MISSING
    assert plan.users.executable is False
    assert sources.releases == {}
    assert projections.active == {}


def test_users_snapshot_is_self_contained_and_not_blocked_by_profiles_projection():
    planner, sources, _projections, _ = setup(snapshots=lambda: ('snapshot-1',))
    publish(sources, 'profiles', 'access', 'navigation', 'tools', 'registry', 'definitions')
    plan = planner.inspect()
    items = by_name(plan)
    assert items['access'].state is ProjectionPlanState.BLOCKED
    assert items['registry'].state is ProjectionPlanState.BLOCKED
    assert plan.users.state is UsersPlanState.SNAPSHOT_SELECTION_REQUIRED
    assert plan.users.executable is True
    assert plan.users.snapshot_ids == ('snapshot-1',)


def test_replanning_uses_exact_dependency_targets_and_users_remains_executable():
    planner, sources, projections, _ = setup(snapshots=lambda: ('approved-1',))
    publish(sources, 'profiles', 'access', 'tools', 'registry', 'definitions')
    activate(sources, projections, 'profiles')
    activate(sources, projections, 'tools')
    first = planner.inspect()
    assert [entry.key.value for entry in first.ready] == ['access', 'registry']
    activate(sources, projections, 'registry', 'tools')
    second = planner.inspect()
    assert by_name(second)['definitions'].state is ProjectionPlanState.NEVER_PROJECTED
    assert second.users.executable is True
    assert json.dumps(second.to_dict())


def test_outdated_parent_blocks_consumer_until_parent_is_reprojected():
    planner, sources, projections, _ = setup(snapshots=lambda: ('approved',))
    publish(sources, 'profiles', 'access')
    activate(sources, projections, 'profiles')
    activate(sources, projections, 'access', 'profiles')
    sources.releases[key('profiles')] = release('profiles-r2')
    stale = by_name(planner.inspect())
    assert stale['profiles'].state is ProjectionPlanState.OUTDATED
    assert stale['access'].state is ProjectionPlanState.BLOCKED


def test_provider_failure_is_fail_closed_without_private_error_text():
    planner, sources, projections, _ = setup()
    publish(sources, 'profiles', 'navigation')
    sources.failed.add(key('profiles'))
    projections.failed.add(key('navigation'))
    plan = planner.inspect()
    assert by_name(plan)['profiles'].state is ProjectionPlanState.UNAVAILABLE
    assert by_name(plan)['navigation'].state is ProjectionPlanState.UNAVAILABLE
    assert 'private' not in json.dumps(plan.to_dict())


def test_invalid_snapshot_catalog_is_unavailable():
    for catalog in (
        lambda: ('duplicate', 'duplicate'),
        lambda: ['not-a-tuple'],
        lambda: (_ for _ in ()).throw(OSError('private location')),
    ):
        planner, sources, projections, _ = setup(snapshots=catalog)
        publish(sources, 'profiles')
        activate(sources, projections, 'profiles')
        assert planner.inspect().users.state is UsersPlanState.CATALOG_UNAVAILABLE
