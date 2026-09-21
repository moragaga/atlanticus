import pytest

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


def principal(subject_id: str = 'manager-user') -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id=subject_id,
        display_name=subject_id,
        access_keys=('alarms.manage',),
    )


def test_alarm_configuration_workspace_round_trips_payload_for_owner() -> None:
    binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=principal,
    )
    payload = configuration().to_document()

    document = binding.save_payload(None, payload)

    assert binding.load_payload(document) == payload


def test_alarm_configuration_workspace_rejects_another_owner() -> None:
    owner_binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=principal,
    )
    document = owner_binding.save_payload(None, configuration().to_document())
    foreign_binding = AlarmConfigurationManagerWorkspaceBinding(
        source=SourceWorkflowStub(),
        principal_provider=lambda: principal('another-user'),
    )

    with pytest.raises(ManagerProjectionError, match='belongs to another user'):
        foreign_binding.load_payload(document)
