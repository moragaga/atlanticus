from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.web.compositions.navigation_manager.workspace import (
    NavigationManagerWorkspaceBinding,
)
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspace
from atlanticus.web.source.models import SourceKey, SourceSnapshot


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='tester',
        display_name='Tester',
        is_local=True,
    )


def test_workspace_binding_creates_manager_workspace_on_current_source_base() -> None:
    snapshot = SourceSnapshot(SourceKey('navigation-configuration'), None, None)
    source = SimpleNamespace(
        source_key=snapshot.source_key,
        get_source_snapshot=lambda: snapshot,
    )
    binding = NavigationManagerWorkspaceBinding(
        source=source,
        principal_provider=_principal,
    )
    payload = {'links': [], 'groups': []}

    document = binding.save_payload(None, payload)
    workspace = ManagerWorkspace.from_document(document)

    assert workspace.owner_subject_id == 'tester'
    assert workspace.base == snapshot
    assert workspace.payload == payload


def test_workspace_binding_updates_only_payload_and_preserves_source_base() -> None:
    snapshot = SourceSnapshot(SourceKey('navigation-configuration'), None, None)
    source = SimpleNamespace(
        source_key=snapshot.source_key,
        get_source_snapshot=lambda: snapshot,
    )
    binding = NavigationManagerWorkspaceBinding(
        source=source,
        principal_provider=_principal,
    )
    original = ManagerWorkspace.create(
        owner_subject_id='tester',
        payload={'links': [], 'groups': []},
        base=snapshot,
        saved_at_utc=datetime(2026, 9, 15, 12, tzinfo=UTC),
    )
    updated_payload = {'links': [{'key': 'x'}], 'groups': []}

    updated = ManagerWorkspace.from_document(
        binding.save_payload(original.to_document(), updated_payload)
    )

    assert updated.base == original.base
    assert updated.base_payload_revision == original.base_payload_revision
    assert updated.payload == updated_payload
