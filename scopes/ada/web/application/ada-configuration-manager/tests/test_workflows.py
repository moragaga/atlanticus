import pytest

from ada.web.application.configuration_manager.workflows import (
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
)
from atlanticus.web.manager import build_workspace_revision
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
)
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.errors import SourceConcurrencyError
from atlanticus.web.source.models import SourceKey


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
    workflow = NavigationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'local'
    )

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
