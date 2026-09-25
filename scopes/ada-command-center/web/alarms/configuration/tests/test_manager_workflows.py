from datetime import UTC, datetime

import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyEntry, ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationSourceError
from ada_command_center.web.alarms.configuration.tool_dependencies import (
    WORKSPACE_TOOL_CATALOG_REVISION_KEY,
    pin_workspace_tool_catalog_revision,
)
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolReferenceCatalog,
)
from ada_command_center.web.alarms.configuration.workflows import (
    AlarmConfigurationManagerDraftValidationWorkflow,
    AlarmConfigurationManagerSourceWorkflow,
)
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryPage,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)

from .helpers import configuration


def _release_ref(value: str) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 21, 13, 0, tzinfo=UTC),
    )


def _dependency(tool_key: str = 'tool_a') -> ToolDependencyEntry:
    return ToolDependencyEntry(
        tool_key=tool_key,
        display_name='Tool A',
        source_release_id='tool-a-r1',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=ToolStructure(
            tool_key=tool_key,
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine',
                    display_name='Mine',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='crusher', display_name='Crusher'),),
                ),
            ),
        ),
    )


def _tool_references(revision: str = 'tools-r2') -> AlarmToolReferenceCatalog:
    return AlarmToolReferenceCatalog(
        catalog_revision=revision,
        tools=(),
        dependencies=ToolDependencyManifest(
            confirmed_tool_catalog_revision=revision,
            tools=(_dependency(),),
        ),
    )


class ToolReferenceProvider:
    def __init__(self, revision: str = 'tools-r2') -> None:
        self.revision = revision

    def __call__(self) -> AlarmToolReferenceCatalog:
        return _tool_references(self.revision)


class AlarmSourceServiceStub:
    def __init__(self) -> None:
        self.source_key = SourceKey('alarm-configuration')
        self.release_ref = _release_ref('current')
        self.snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=SourceReleaseSummary(
                release_ref=self.release_ref,
                content_hash=Digest('sha256', 'abc'),
            ),
            concurrency_token=ConcurrencyToken('etag-1'),
        )
        self.publish_args = None

    def get_current(self):
        return self.snapshot

    def load_release(self, release_ref):
        assert release_ref == self.release_ref
        return type(
            'Release',
            (),
            {
                'release_ref': self.release_ref,
                'snapshot': AlarmConfigurationSnapshot(
                    configuration=configuration(),
                    tool_dependencies=ToolDependencyManifest(
                        confirmed_tool_catalog_revision='tools-r1',
                        tools=(),
                    ),
                ),
            },
        )()

    def query_history(self, *, page_size, cursor=None):
        assert page_size == 10
        assert cursor is None
        return HistoryPage(items=())

    def publish_snapshot(
        self,
        value,
        *,
        published_by,
        expected_concurrency_token,
        basis_release,
    ):
        self.publish_args = (
            value,
            published_by,
            expected_concurrency_token,
            basis_release,
        )
        published_ref = _release_ref('published')
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.source_key,
            release_ref=published_ref,
            content_hash=Digest('sha256', 'def'),
            resources=(),
            basis_release=basis_release,
        )
        snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=SourceReleaseSummary(
                release_ref=published_ref,
                content_hash=metadata.content_hash,
            ),
            concurrency_token=ConcurrencyToken('etag-2'),
        )
        return PublishResult(release=metadata, snapshot=snapshot)


def test_alarm_configuration_manager_validation_uses_pinned_tool_catalog() -> None:
    provider = ToolReferenceProvider()
    workflow = AlarmConfigurationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=provider,
    )
    valid_payload = pin_workspace_tool_catalog_revision(
        configuration().to_document(),
        'tools-r2',
    )
    invalid_payload = pin_workspace_tool_catalog_revision(
        {'rules': 'invalid', 'messages': []},
        'tools-r2',
    )

    valid = workflow.validate_draft(valid_payload)
    invalid = workflow.validate_draft(invalid_payload)

    assert valid.valid is True
    assert tuple((item.label, item.value) for item in valid.summary) == (
        ('Rules', '1'),
        ('Active rules', '1'),
        ('Messages', '1'),
    )
    assert invalid.valid is False
    assert invalid.issues[0].code == 'alarm.configuration.invalid'


def test_alarm_configuration_manager_validation_rejects_tool_catalog_drift() -> None:
    provider = ToolReferenceProvider('tools-r3')
    workflow = AlarmConfigurationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=provider,
    )
    payload = pin_workspace_tool_catalog_revision(
        configuration().to_document(),
        'tools-r2',
    )

    result = workflow.validate_draft(payload)

    assert result.valid is False
    assert result.issues[0].code == 'alarm.tools.catalog_changed'


def test_alarm_configuration_manager_source_loads_current_tool_revision_sidecar() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=_tool_references,
    )

    result = workflow.load_current_source()

    assert result.snapshot == source.snapshot
    assert result.payload is not None
    assert result.payload[WORKSPACE_TOOL_CATALOG_REVISION_KEY] == 'tools-r2'


def test_alarm_configuration_manager_source_publishes_selected_tool_manifest() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=_tool_references,
    )

    result = workflow.publish_draft(
        pin_workspace_tool_catalog_revision(
            configuration().to_document(),
            'tools-r2',
        ),
        source.snapshot,
    )

    assert source.publish_args is not None
    value, actor, token, basis = source.publish_args
    assert value.configuration == configuration()
    assert value.confirmed_tool_catalog_revision == 'tools-r2'
    assert tuple(tool.tool_key for tool in value.tool_dependencies.tools) == ('tool_a',)
    assert value.tool_dependencies.get('tool_a').display_name == 'Tool A'
    assert actor == 'manager-user'
    assert token == source.snapshot.concurrency_token
    assert basis == source.release_ref
    assert result.audit.actor == 'manager-user'
    assert result.source.snapshot.current is not None
    assert result.source.snapshot.current.release_ref.release_id.value == 'published'


def test_alarm_configuration_manager_source_rejects_tool_drift_before_publish() -> None:
    source = AlarmSourceServiceStub()
    provider = ToolReferenceProvider('tools-r3')
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=provider,
    )

    with pytest.raises(
        AlarmConfigurationSourceError,
        match='changed after Alarm Configuration validation',
    ):
        workflow.publish_draft(
            pin_workspace_tool_catalog_revision(
                configuration().to_document(),
                'tools-r2',
            ),
            source.snapshot,
        )

    assert source.publish_args is None


def test_alarm_configuration_manager_source_delegates_history() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
        tool_reference_provider=_tool_references,
    )

    page = workflow.list_history(limit=10)

    assert page.items == ()
