import pytest

from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.tool_dependencies import (
    WORKSPACE_TOOL_CATALOG_REVISION_KEY,
)
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolReferenceCatalog,
)
from ada_command_center.web.alarms.configuration.workspace import (
    AlarmConfigurationManagerWorkspaceBinding,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.source.models import SourceKey, SourceSnapshot

from .helpers import configuration


class SourceWorkflowStub:
    source_key = SourceKey('alarm-configuration')

    def get_source_snapshot(self):
        return SourceSnapshot(
            source_key=self.source_key,
            current=None,
            concurrency_token=None,
        )


class ToolReferenceProvider:
    def __init__(self, revision: str = 'tools-r2') -> None:
        self.revision = revision

    def __call__(self) -> AlarmToolReferenceCatalog:
        return AlarmToolReferenceCatalog(
            catalog_revision=self.revision,
            tools=(),
            dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision=self.revision,
                tools=(),
            ),
        )


def principal(subject_id: str = 'manager-user') -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id=subject_id,
        display_name=subject_id,
        access_keys=('alarms.manage',),
    )


def test_alarm_configuration_workspace_pins_tool_revision_for_owner() -> None:
    provider = ToolReferenceProvider()
    binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=principal,
        tool_reference_provider=provider,
    )
    payload = configuration().to_document()

    document = binding.save_payload(None, payload)
    loaded = binding.load_payload(document)

    assert loaded is not None
    assert loaded[WORKSPACE_TOOL_CATALOG_REVISION_KEY] == 'tools-r2'
    assert AlarmConfiguration.from_document(loaded) == configuration()


def test_alarm_configuration_workspace_repins_revision_on_next_save() -> None:
    provider = ToolReferenceProvider('tools-r2')
    binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=principal,
        tool_reference_provider=provider,
    )
    document = binding.save_payload(None, configuration().to_document())

    provider.revision = 'tools-r3'
    document = binding.save_payload(document, configuration().to_document())
    loaded = binding.load_payload(document)

    assert loaded is not None
    assert loaded[WORKSPACE_TOOL_CATALOG_REVISION_KEY] == 'tools-r3'


def test_alarm_configuration_workspace_rejects_another_owner() -> None:
    provider = ToolReferenceProvider()
    owner_binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=principal,
        tool_reference_provider=provider,
    )
    document = owner_binding.save_payload(None, configuration().to_document())
    foreign_binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=lambda: principal('another-user'),
        tool_reference_provider=provider,
    )

    with pytest.raises(ManagerProjectionError, match='belongs to another user'):
        foreign_binding.load_payload(document)
