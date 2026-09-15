from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.manager.source import SourceReadResult
from atlanticus.web.manager.workspace import ManagerWorkspace, ManagerWorkspaceController
from atlanticus.web.source.models import SourceKey, SourceSnapshot


class Coordinator:
    def __init__(self) -> None:
        self.source = SourceReadResult(
            SourceSnapshot(SourceKey('tools'), None, None),
            None,
        )

    def load_current_source(self, _module_key, _principal):
        return self.source


def _principal(subject_id: str) -> ManagerPrincipal:
    return ManagerPrincipal(subject_id=subject_id, display_name=subject_id)


def _workspace(owner_subject_id: str) -> ManagerWorkspace:
    return ManagerWorkspace.create(
        owner_subject_id=owner_subject_id,
        payload={'value': 'draft'},
        base=SourceSnapshot(SourceKey('tools'), None, None),
    )


def test_foreign_browser_workspace_does_not_block_current_principal_hydration() -> None:
    principal = _principal('principal-current')
    foreign = _workspace('principal-other')
    controller = ManagerWorkspaceController(Coordinator())

    assert controller.safe_workspace(foreign.to_document(), principal) is None
    assert (
        controller.has_local_work(
            module_key='tools',
            principal=principal,
            workspace_document=foreign.to_document(),
            editor_revision='stale-editor-revision',
        )
        is False
    )


def test_invalid_browser_workspace_does_not_block_source_hydration() -> None:
    principal = _principal('principal-current')
    controller = ManagerWorkspaceController(Coordinator())

    assert (
        controller.has_local_work(
            module_key='tools',
            principal=principal,
            workspace_document={'schema_version': 1},
            editor_revision='stale-editor-revision',
        )
        is False
    )


def test_unsaved_editor_without_browser_workspace_is_local_work() -> None:
    principal = _principal('principal-current')
    controller = ManagerWorkspaceController(Coordinator())

    assert (
        controller.has_local_work(
            module_key='tools',
            principal=principal,
            workspace_document=None,
            editor_revision='unsaved-editor-revision',
        )
        is True
    )
