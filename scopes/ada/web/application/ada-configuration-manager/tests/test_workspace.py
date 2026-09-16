import pytest

from ada.web.application.configuration_manager.workspace import ManagerWorkspaceBridge
from atlanticus.web.manager import ManagerProjectionError, ManagerWorkspace
from atlanticus.web.source.models import SourceKey, SourceSnapshot


def test_bridge_creates_workspace_on_current_source_snapshot() -> None:
    snapshot = SourceSnapshot(SourceKey('tools'), None, None)
    bridge = ManagerWorkspaceBridge(
        owner_subject_id_provider=lambda: 'local',
        source_snapshot_provider=lambda: snapshot,
    )

    document = bridge.write_payload(None, {'tool_key': 'tool-a'})
    workspace = ManagerWorkspace.from_document(document)

    assert workspace.owner_subject_id == 'local'
    assert workspace.base == snapshot
    assert workspace.payload == {'tool_key': 'tool-a'}
    assert bridge.read_payload(document) == {'tool_key': 'tool-a'}


def test_bridge_updates_payload_without_rebasing_source() -> None:
    base = SourceSnapshot(SourceKey('tools'), None, None)
    bridge = ManagerWorkspaceBridge(
        owner_subject_id_provider=lambda: 'local',
        source_snapshot_provider=lambda: SourceSnapshot(SourceKey('tools'), None, None),
    )
    first = bridge.write_payload(None, {'value': 1})
    first_workspace = ManagerWorkspace.from_document(first)

    updated = bridge.write_payload(first, {'value': 2})
    updated_workspace = ManagerWorkspace.from_document(updated)

    assert first_workspace.base == base
    assert updated_workspace.base == first_workspace.base
    assert updated_workspace.payload == {'value': 2}


def test_bridge_rejects_workspace_from_another_user() -> None:
    snapshot = SourceSnapshot(SourceKey('tools'), None, None)
    foreign = ManagerWorkspace.create(
        owner_subject_id='other',
        payload={'value': 1},
        base=snapshot,
    ).to_document()
    bridge = ManagerWorkspaceBridge(
        owner_subject_id_provider=lambda: 'local',
        source_snapshot_provider=lambda: snapshot,
    )

    with pytest.raises(ManagerProjectionError, match='another user'):
        bridge.read_payload(foreign)
