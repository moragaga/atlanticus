from datetime import UTC, datetime
from types import SimpleNamespace

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
        return SimpleNamespace(
            release_ref=self.release_ref,
            configuration=configuration(),
        )

    def query_history(self, *, page_size, cursor=None):
        assert page_size == 10
        assert cursor is None
        return HistoryPage(items=())

    def publish_configuration(
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


def test_alarm_configuration_manager_validation_uses_intrinsic_contract() -> None:
    workflow = AlarmConfigurationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'manager-user'
    )

    valid = workflow.validate_draft(configuration().to_document())
    invalid = workflow.validate_draft({'rules': 'invalid', 'messages': []})

    assert valid.valid is True
    assert tuple((item.label, item.value) for item in valid.summary) == (
        ('Rules', '1'),
        ('Active rules', '1'),
        ('Messages', '1'),
    )
    assert invalid.valid is False
    assert invalid.issues[0].code == 'alarm.configuration.invalid'


def test_alarm_configuration_manager_source_loads_exact_current_payload() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.load_current_source()

    assert result.snapshot == source.snapshot
    assert result.payload == configuration().to_document()


def test_alarm_configuration_manager_source_publishes_with_current_snapshot() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.publish_draft(
        configuration().to_document(),
        source.snapshot,
    )

    assert source.publish_args is not None
    value, actor, token, basis = source.publish_args
    assert value == configuration()
    assert actor == 'manager-user'
    assert token == source.snapshot.concurrency_token
    assert basis == source.release_ref
    assert result.audit.actor == 'manager-user'
    assert result.source.snapshot.current is not None
    assert result.source.snapshot.current.release_ref.release_id.value == 'published'


def test_alarm_configuration_manager_source_delegates_history() -> None:
    source = AlarmSourceServiceStub()
    workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'manager-user',
    )

    page = workflow.list_history(limit=10)

    assert page.items == ()
