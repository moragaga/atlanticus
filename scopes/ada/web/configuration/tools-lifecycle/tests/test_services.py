from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.tools import ToolConfigurationValidationError
from ada.configuration.tools_lifecycle import (
    ToolAdministrationService,
    ToolConfigurationProjectionSnapshot,
    ToolConfigurationSourceSnapshot,
    ToolLifecycleProjectionError,
    ToolLifecycleSourceError,
    ToolProjectionWorkflow,
)

from .helpers import configuration_without_structure, valid_configuration


class SourceStub:
    def __init__(self, document: ToolConfigurationSourceSnapshot | None = None) -> None:
        self.document = document

    def load(self) -> ToolConfigurationSourceSnapshot | None:
        return self.document


class PublisherStub:
    def __init__(self, source: SourceStub) -> None:
        self.source = source
        self.calls = 0

    def publish(
        self,
        document: ToolConfigurationSourceSnapshot,
        *,
        expected_revision: str | None,
    ) -> None:
        current = self.source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_revision:
            raise RuntimeError('source conflict')
        self.calls += 1
        self.source.document = document


class ProjectionStub:
    def __init__(
        self,
        projection: ToolConfigurationProjectionSnapshot | None = None,
    ) -> None:
        self.projection = projection
        self.save_calls = 0

    def load(self) -> ToolConfigurationProjectionSnapshot | None:
        return self.projection

    def save(
        self,
        projection: ToolConfigurationProjectionSnapshot,
    ) -> ToolConfigurationProjectionSnapshot:
        self.save_calls += 1
        self.projection = projection
        return projection

    def health_check(self) -> bool:
        return True


def source_snapshot() -> ToolConfigurationSourceSnapshot:
    return ToolConfigurationSourceSnapshot.create(
        configuration=valid_configuration(),
        saved_by='source-user',
        saved_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )


def test_validation_reuses_current_ada_operational_boundary() -> None:
    source = SourceStub()
    service = ToolAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.validate_configuration(configuration_without_structure())

    assert result.valid is False
    assert len(result.issues) == 1
    assert result.issues[0].code == 'tool.invalid'
    assert 'requires Tool Structure' in result.issues[0].message


def test_publish_writes_valid_configuration_with_cas() -> None:
    source = SourceStub()
    publisher = PublisherStub(source)
    service = ToolAdministrationService(
        source=source,
        publisher=publisher,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.publish_configuration(
        valid_configuration(),
        expected_source_revision=None,
    )

    assert result.published is True
    assert publisher.calls == 1
    assert source.document is not None
    assert source.document.saved_by == 'manager-user'


def test_publish_skips_identical_configuration() -> None:
    current = source_snapshot()
    source = SourceStub(current)
    publisher = PublisherStub(source)
    service = ToolAdministrationService(
        source=source,
        publisher=publisher,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.publish_configuration(
        current.configuration,
        expected_source_revision=current.revision,
    )

    assert result.published is False
    assert publisher.calls == 0
    assert result.source_revision == current.revision


def test_publish_rejects_changed_source_revision() -> None:
    current = source_snapshot()
    source = SourceStub(current)
    service = ToolAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(
        ToolLifecycleSourceError,
        match='Tool source revision changed before publication',
    ):
        service.publish_configuration(
            current.configuration,
            expected_source_revision='stale',
        )


def test_publish_rejects_invalid_operational_configuration() -> None:
    source = SourceStub()
    service = ToolAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(
        ToolConfigurationValidationError,
        match='Tool Configuration must be valid before publication',
    ):
        service.publish_configuration(
            configuration_without_structure(),
            expected_source_revision=None,
        )


def test_status_preserves_source_and_projection_metadata() -> None:
    current = source_snapshot()
    active = ToolConfigurationProjectionSnapshot.create(
        configuration=current.configuration,
        source_revision=current.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
    )
    workflow = ToolProjectionWorkflow(
        source=SourceStub(current),
        projection=ProjectionStub(active),
        audit_actor_provider=lambda: 'manager-user',
    )

    status = workflow.get_status()

    assert status.source_revision == current.revision
    assert status.source_audit is not None
    assert status.source_audit.actor == 'source-user'
    assert status.active_revision == active.revision
    assert status.active_source_revision == current.revision
    assert status.projection_audit is not None
    assert status.projection_audit.actor == 'projector'


def test_project_creates_snapshot_for_expected_source() -> None:
    current = source_snapshot()
    repository = ProjectionStub()
    workflow = ToolProjectionWorkflow(
        source=SourceStub(current),
        projection=repository,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.project(current.revision)

    assert result.projected is True
    assert repository.save_calls == 1
    assert repository.projection is not None
    assert repository.projection.source_revision == current.revision
    assert repository.projection.configuration == current.configuration


def test_project_skips_synchronized_projection() -> None:
    current = source_snapshot()
    active = ToolConfigurationProjectionSnapshot.create(
        configuration=current.configuration,
        source_revision=current.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
    )
    repository = ProjectionStub(active)
    workflow = ToolProjectionWorkflow(
        source=SourceStub(current),
        projection=repository,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.project(current.revision)

    assert result.projected is False
    assert result.projection_revision == active.revision
    assert repository.save_calls == 0


def test_project_requires_existing_source() -> None:
    workflow = ToolProjectionWorkflow(
        source=SourceStub(),
        projection=ProjectionStub(),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(ToolLifecycleSourceError, match='Tool source does not exist'):
        workflow.project('expected')


def test_project_rejects_stale_source_revision() -> None:
    current = source_snapshot()
    workflow = ToolProjectionWorkflow(
        source=SourceStub(current),
        projection=ProjectionStub(),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(
        ToolLifecycleProjectionError,
        match='Tool source revision changed before projection',
    ):
        workflow.project('stale')
