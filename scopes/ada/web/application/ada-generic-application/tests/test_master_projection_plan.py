from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from ada.web.application.generic.master_projection.plan import (
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

    def publish(self, *args, **kwargs):
        raise AssertionError('The planner must never publish sources')


class Projections:
    def __init__(self):
        self.active = {}
        self.failed = set()

    def get_active(self, source_key):
        if source_key in self.failed:
            raise ConnectionError('private projection connection details')
        return self.active.get(source_key)

    def replace_active(self, *args, **kwargs):
        raise AssertionError('The planner must never replace projections')


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

    def project(self, *args, **kwargs):
        raise AssertionError('The planner must never project anything')


def projected(target):
    return ProjectionRecord(
        source_key=target.source_key,
        source_release_id=target.source_release_id,
        source_published_at_utc=target.source_release.published_at_utc,
        projected_at_utc=NOW,
        payload=object(),
        dependencies=target.dependencies,
    )


def setup(domains=None, snapshots=None):
    requirements = domains or {
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


def by_name(plan):
    return {entry.key.value: entry for entry in plan.entries}


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


def test_empty_environment_is_read_only_and_reports_missing_sources():
    planner, sources, projections, _ = setup(snapshots=lambda: ())
    plan = planner.inspect()
    assert len(plan.entries) == 6
    assert {entry.state for entry in plan.entries} == {ProjectionPlanState.SOURCE_MISSING}
    assert plan.ready == ()
    assert plan.users.state is UsersPlanState.SNAPSHOT_MISSING
    assert all(value is None for value in projections.active.values())
    assert sources.releases == {}


def test_ready_roots_and_blocked_consumers_are_derived_from_prerequisites():
    planner, sources, _projections, _ = setup(snapshots=lambda: ('snapshot-1',))
    publish(sources, 'profiles', 'access', 'navigation', 'tools', 'registry', 'definitions')
    plan = planner.inspect()
    items = by_name(plan)
    assert {item.key.value for item in plan.ready} == {'navigation', 'profiles', 'tools'}
    assert items['access'].blocked_by == (key('profiles'),)
    assert items['registry'].blocked_by == (key('tools'),)
    assert items['definitions'].blocked_by == (key('registry'),)
    assert items['access'].current_target is None
    assert plan.users.state is UsersPlanState.PROFILES_PENDING


def test_replanning_uses_real_exact_dependency_targets_after_each_projection():
    planner, sources, projections, _ = setup(snapshots=lambda: ('approved-1',))
    publish(sources, 'profiles', 'access', 'tools', 'registry', 'definitions')
    activate(sources, projections, 'profiles')
    activate(sources, projections, 'tools')
    first = planner.inspect()
    assert [entry.key.value for entry in first.ready] == ['access', 'registry']
    assert first.users.state is UsersPlanState.SNAPSHOT_SELECTION_REQUIRED
    assert by_name(first)['definitions'].state is ProjectionPlanState.BLOCKED
    activate(sources, projections, 'registry', 'tools')
    second = planner.inspect()
    assert by_name(second)['registry'].state is ProjectionPlanState.CURRENT
    assert by_name(second)['definitions'].state is ProjectionPlanState.NEVER_PROJECTED
    assert by_name(second)['definitions'].current_target.dependencies == (
        projections.active[key('registry')].target,
    )
    assert second.to_dict()['users']['executable'] is False
    assert json.dumps(second.to_dict())


def test_outdated_parent_blocks_consumers_instead_of_using_old_dependency_target():
    planner, sources, projections, _ = setup(snapshots=lambda: ('approved',))
    publish(sources, 'profiles', 'access')
    activate(sources, projections, 'profiles')
    activate(sources, projections, 'access', 'profiles')
    assert by_name(planner.inspect())['access'].state is ProjectionPlanState.CURRENT
    sources.releases[key('profiles')] = release('profiles-r2')
    stale = by_name(planner.inspect())
    assert stale['profiles'].state is ProjectionPlanState.OUTDATED
    assert stale['access'].state is ProjectionPlanState.BLOCKED
    assert stale['access'].current_target is None
    activate(sources, projections, 'profiles')
    refreshed = by_name(planner.inspect())
    assert refreshed['access'].state is ProjectionPlanState.OUTDATED
    assert refreshed['access'].current_target.dependencies == (
        projections.active[key('profiles')].target,
    )


def test_missing_source_with_orphaned_projection_is_not_reported_current():
    planner, sources, projections, _ = setup()
    publish(sources, 'profiles')
    activate(sources, projections, 'profiles')
    del sources.releases[key('profiles')]
    orphaned = by_name(planner.inspect())['profiles']
    assert orphaned.state is ProjectionPlanState.SOURCE_MISSING
    assert orphaned.projected_target is not None
    assert orphaned.current_target is None


def test_partial_read_outage_is_isolated_and_hides_sensitive_exception_text():
    planner, sources, projections, _ = setup()
    publish(sources, 'profiles', 'access', 'tools', 'navigation')
    sources.failed.add(key('profiles'))
    projections.failed.add(key('navigation'))
    plan = planner.inspect()
    items = by_name(plan)
    assert items['profiles'].state is ProjectionPlanState.UNAVAILABLE
    assert items['navigation'].state is ProjectionPlanState.UNAVAILABLE
    assert items['access'].state is ProjectionPlanState.BLOCKED
    assert items['tools'].state is ProjectionPlanState.NEVER_PROJECTED
    assert 'private' not in json.dumps(plan.to_dict())


def test_selector_contract_mismatch_is_fail_closed():
    planner, sources, projections, selectors = setup()
    publish(sources, 'profiles', 'access')
    activate(sources, projections, 'profiles')
    selectors['access'].override = ProjectionTarget(key('access'), sources.releases[key('access')])
    item = by_name(planner.inspect())['access']
    assert item.state is ProjectionPlanState.UNAVAILABLE
    assert item.error_type == 'TARGET_CHANGED_OR_INCOMPATIBLE'
    assert item.current_target is None


def test_source_changed_during_selection_never_returns_stale_ready_target():
    planner, sources, _projections, _ = setup()
    publish(sources, 'profiles')
    sources.after_read[key('profiles')] = release('profiles-r2')
    item = by_name(planner.inspect())['profiles']
    assert item.state is ProjectionPlanState.UNAVAILABLE
    assert item.error_type == 'TARGET_CHANGED_OR_INCOMPATIBLE'


def test_invalid_graph_rejected_before_any_provider_reads():
    roots = {'profiles': (), 'access': ('profiles',)}
    _planner, sources, projections, selectors = setup(domains=roots)
    domains = (
        ProjectionDomain(
            key('profiles'), sources, projections, selectors['profiles'], (key('access'),)
        ),
        ProjectionDomain(
            key('access'), sources, projections, selectors['access'], (key('profiles'),)
        ),
    )
    with pytest.raises(ValueError, match='cycle'):
        MasterProjectionPlanner(domains=domains, profiles_key=key('profiles'))
    with pytest.raises(ValueError, match='unique'):
        MasterProjectionPlanner(domains=(domains[0], domains[0]), profiles_key=key('profiles'))
    unknown = ProjectionDomain(
        key('profiles'), sources, projections, selectors['profiles'], (key('missing'),)
    )
    with pytest.raises(ValueError, match='not registered'):
        MasterProjectionPlanner(domains=(unknown,), profiles_key=key('profiles'))


def test_invalid_or_unavailable_snapshot_catalog_cannot_enable_users():
    for catalog in (
        lambda: ('duplicate', 'duplicate'),
        lambda: ['not-a-tuple'],
        lambda: (_ for _ in ()).throw(OSError('private location')),
    ):
        planner, sources, projections, _ = setup(snapshots=catalog)
        publish(sources, 'profiles')
        activate(sources, projections, 'profiles')
        assert planner.inspect().users.state is UsersPlanState.CATALOG_UNAVAILABLE
