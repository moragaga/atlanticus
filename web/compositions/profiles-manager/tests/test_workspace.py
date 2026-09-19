from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.web.compositions.profiles_manager.workspace import ProfilesManagerWorkspaceBinding
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
    snapshot = SourceSnapshot(SourceKey('profiles-configuration'), None, None)
    source = SimpleNamespace(
        source_key=snapshot.source_key,
        get_source_snapshot=lambda: snapshot,
    )
    binding = ProfilesManagerWorkspaceBinding(
        source=source,
        principal_provider=_principal,
    )
    payload = {'profiles': []}

    document = binding.save_payload(None, payload)
    workspace = ManagerWorkspace.from_document(document)

    assert workspace.owner_subject_id == 'tester'
    assert workspace.base == snapshot
    assert workspace.payload == payload


def test_workspace_binding_updates_only_payload_and_preserves_source_base() -> None:
    snapshot = SourceSnapshot(SourceKey('profiles-configuration'), None, None)
    source = SimpleNamespace(
        source_key=snapshot.source_key,
        get_source_snapshot=lambda: snapshot,
    )
    binding = ProfilesManagerWorkspaceBinding(
        source=source,
        principal_provider=_principal,
    )
    original = ManagerWorkspace.create(
        owner_subject_id='tester',
        payload={'profiles': []},
        base=snapshot,
        saved_at_utc=datetime(2026, 9, 19, 12, tzinfo=UTC),
    )
    updated_payload = {
        'profiles': [
            {
                'key': '11111111-1111-4111-8111-111111111111',
                'label': 'Analista',
                'background_color': '#123456',
                'text_color': '#FFFFFF',
            }
        ]
    }

    updated = ManagerWorkspace.from_document(
        binding.save_payload(original.to_document(), updated_payload)
    )

    assert updated.base == original.base
    assert updated.base_payload_revision == original.base_payload_revision
    assert updated.payload == updated_payload
