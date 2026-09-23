import pytest

from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolReferenceCatalog,
)
from ada_command_center.web.alarms.configuration.web.authoring import (
    empty_authoring_document,
)
from ada_command_center.web.alarms.configuration.web.callbacks import (
    register_alarm_configuration_admin_callbacks,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from ada_command_center.web.alarms.configuration.workspace import (
    AlarmConfigurationManagerWorkspaceBinding,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerWorkspace
from atlanticus.web.source.models import SourceKey, SourceSnapshot

from .helpers import configuration


class CallbackAppStub:
    def __init__(self) -> None:
        self.callbacks: dict[str, object] = {}
        self.options: dict[str, dict[str, object]] = {}

    def callback(self, *_args, **options):
        def register(callback):
            self.callbacks[callback.__name__] = callback
            self.options[callback.__name__] = options
            return callback

        return register


class SourceWorkflowStub:
    source_key = SourceKey('alarm-configuration')

    def get_source_snapshot(self) -> SourceSnapshot:
        return SourceSnapshot(
            source_key=self.source_key,
            current=None,
            concurrency_token=None,
        )


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='manager-user',
        display_name='Manager User',
        access_keys=('alarms.manage',),
    )


def _tool_references() -> AlarmToolReferenceCatalog:
    return AlarmToolReferenceCatalog(
        catalog_revision='tools-r2',
        tools=(),
        dependencies=ToolDependencyManifest(
            confirmed_tool_catalog_revision='tools-r2',
            tools=(),
        ),
    )


def _context() -> tuple[
    AlarmConfigurationAdminWebContext,
    AlarmConfigurationManagerWorkspaceBinding,
]:
    binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=_principal,
        tool_reference_provider=_tool_references,
    )
    return (
        AlarmConfigurationAdminWebContext(
            workspace_payload_reader=binding.load_payload,
            workspace_payload_writer=binding.save_payload,
            draft_store_id='draft-store',
            saved_draft_store_id='saved-draft-store',
            draft_save_action_id='save-draft-action',
            editor_revision_store_id='editor-revision-store',
        ),
        binding,
    )


def _registered_callbacks():
    context, binding = _context()
    app = CallbackAppStub()
    register_alarm_configuration_admin_callbacks(app, context)
    return app, binding


def test_browser_draft_waits_for_manager_hydration_before_initial_load() -> None:
    app, _binding = _registered_callbacks()
    callback = app.callbacks['load_browser_draft']

    assert app.options['load_browser_draft']['prevent_initial_call'] is True
    assert callback(None) == empty_authoring_document()


def test_browser_draft_loads_exact_manager_workspace_payload() -> None:
    app, binding = _registered_callbacks()
    callback = app.callbacks['load_browser_draft']
    expected = configuration().to_document()
    workspace_document = binding.save_payload(None, expected)

    assert callback(workspace_document) == expected


def test_browser_draft_does_not_mask_invalid_manager_workspace() -> None:
    app, _binding = _registered_callbacks()
    callback = app.callbacks['load_browser_draft']

    with pytest.raises(ManagerProjectionError, match='browser workspace is invalid'):
        callback(configuration().to_document())


def test_editor_revision_requires_manager_workspace() -> None:
    app, binding = _registered_callbacks()
    callback = app.callbacks['track_editor_revision']
    expected = configuration().to_document()
    workspace_document = binding.save_payload(None, expected)
    workspace = ManagerWorkspace.from_document(workspace_document)

    assert callback(empty_authoring_document(), None) is None
    assert callback(expected, workspace_document) == workspace.revision
