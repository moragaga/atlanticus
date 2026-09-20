from datetime import UTC, datetime

import pytest

from ada.web.access.configuration import AdaAccessConfiguration, AdaAccessSourceService
from ada.web.application.configuration_manager.access import (
    AdaAccessManagerDraftValidationWorkflow,
    AdaAccessManagerSourceWorkflow,
)
from ada.web.application.configuration_manager.workflows import (
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
)
from atlanticus.web.manager import build_workspace_revision
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
)
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.errors import SourceConcurrencyError
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId


class ProjectionStoreStub:
    def __init__(self, value=None) -> None:
        self.value = value

    def get_active(self, source_key):
        if self.value is None:
            return None
        assert self.value.source_key == source_key
        return self.value

    def replace_active(self, projection):
        self.value = projection
        return projection


def _profiles_projection() -> ProjectionRecord[ProfileCatalog]:
    return ProjectionRecord(
        source_key=SourceKey('profiles-configuration'),
        source_release_id=SourceReleaseId('profiles-1'),
        source_published_at_utc=datetime(2026, 9, 19, 10, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 19, 10, 1, tzinfo=UTC),
        payload=ProfileCatalog(
            profiles=(
                ProfileDefinition(
                    key='operator',
                    label='Operator',
                    background_color='#123456',
                ),
            )
        ),
    )


def test_navigation_source_workflow_publishes_reads_and_lists_history(tmp_path) -> None:
    store = LocalSourceStore(LocalSourceSettings(root=tmp_path))
    source = NavigationSourceService(source=store, source_key=SourceKey('navigation'))
    workflow = NavigationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'local',
    )

    initial = workflow.load_current_source()
    assert initial.snapshot.current is None
    assert initial.payload is None

    published = workflow.publish_draft(
        {'links': [], 'groups': []},
        initial.snapshot,
    )
    current = workflow.load_current_source()
    history = workflow.list_history()

    assert current.snapshot == published.source.snapshot
    assert current.payload == {'links': [], 'groups': []}
    assert len(history.items) == 1
    exact = workflow.load_history_release(history.items[0].release_ref)
    assert exact.payload == current.payload


def test_navigation_validation_uses_manager_workspace_revision() -> None:
    payload = {'links': [], 'groups': []}
    workflow = NavigationManagerDraftValidationWorkflow(audit_actor_provider=lambda: 'local')

    result = workflow.validate_draft(payload)

    assert result.valid is True
    assert result.draft_revision == build_workspace_revision(payload)


def test_navigation_publication_rejects_stale_source_snapshot(tmp_path) -> None:
    store = LocalSourceStore(LocalSourceSettings(root=tmp_path))
    source = NavigationSourceService(source=store, source_key=SourceKey('navigation'))
    workflow = NavigationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'local',
    )
    stale = source.get_current()
    source.publish_catalog(
        NavigationConfigurationCatalog(),
        published_by='external',
        expected_concurrency_token=stale.concurrency_token,
        basis_release=None,
    )

    with pytest.raises(SourceConcurrencyError):
        workflow.publish_draft({'links': [], 'groups': []}, stale)


def test_access_source_workflow_publishes_catalog_and_assignments(tmp_path) -> None:
    store = LocalSourceStore(LocalSourceSettings(root=tmp_path))
    source = AdaAccessSourceService(source=store, source_key=SourceKey('ada-access'))
    workflow = AdaAccessManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'local',
    )
    payload = {
        'access_keys': ['alarms.view'],
        'profile_access': [
            {'profile_key': 'operator', 'access_keys': ['alarms.view']},
        ],
    }

    initial = workflow.load_current_source()
    published = workflow.publish_draft(payload, initial.snapshot)
    current = workflow.load_current_source()

    assert published.source.snapshot == current.snapshot
    assert current.payload == payload


def test_access_publication_rejects_stale_source_snapshot(tmp_path) -> None:
    store = LocalSourceStore(LocalSourceSettings(root=tmp_path))
    source = AdaAccessSourceService(source=store, source_key=SourceKey('ada-access'))
    workflow = AdaAccessManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'local',
    )
    stale = source.get_current()
    source.publish_configuration(
        configuration=AdaAccessConfiguration(),
        published_by='external',
        expected_concurrency_token=stale.concurrency_token,
        basis_release=None,
    )

    with pytest.raises(SourceConcurrencyError):
        workflow.publish_draft(
            {'access_keys': [], 'profile_access': []},
            stale,
        )


def test_access_validation_requires_profiles_projection() -> None:
    payload = {'access_keys': ['alarms.view'], 'profile_access': []}
    workflow = AdaAccessManagerDraftValidationWorkflow(
        profiles_projection=ProjectionStoreStub(),
        profiles_source_key=SourceKey('profiles-configuration'),
        audit_actor_provider=lambda: 'local',
    )

    result = workflow.validate_draft(payload)

    assert result.valid is False
    assert result.issues[0].code == 'access.profiles-projection.unavailable'


def test_access_validation_accepts_assignments_to_projected_profiles() -> None:
    profiles = _profiles_projection()
    payload = {
        'access_keys': ['alarms.view'],
        'profile_access': [
            {'profile_key': 'operator', 'access_keys': ['alarms.view']},
        ],
    }
    workflow = AdaAccessManagerDraftValidationWorkflow(
        profiles_projection=ProjectionStoreStub(profiles),
        profiles_source_key=profiles.source_key,
        audit_actor_provider=lambda: 'local',
    )

    result = workflow.validate_draft(payload)

    assert result.valid is True
    assert result.draft_revision == build_workspace_revision(payload)
