from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAdministrationService,
    KpiDefinitionConfiguration,
    KpiDefinitionProjection,
    KpiDefinitionProjectionError,
    KpiDefinitionProjectionWorkflow,
    KpiDefinitionSourceDocument,
    KpiDefinitionSourceError,
    build_kpi_definition_digest,
)


class SourceStub:
    def __init__(self, document: KpiDefinitionSourceDocument | None = None) -> None:
        self.document = document

    def load(self) -> KpiDefinitionSourceDocument | None:
        return self.document


class PublisherStub:
    def __init__(self, source: SourceStub) -> None:
        self.source = source
        self.calls = 0

    def publish(
        self,
        document: KpiDefinitionSourceDocument,
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
    def __init__(self, projection: KpiDefinitionProjection | None = None) -> None:
        self.projection = projection
        self.save_calls = 0

    def load(self) -> KpiDefinitionProjection | None:
        return self.projection

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection:
        self.save_calls += 1
        self.projection = projection
        return projection

    def health_check(self) -> bool:
        return True


def configuration() -> KpiDefinitionConfiguration:
    return KpiDefinitionConfiguration(
        definitions=(
            KpiDefinition(
                kpi_key='throughput',
                fields={'name': 'Throughput', 'description': 'Hourly throughput'},
            ),
            KpiDefinition(
                kpi_key='recovery',
                fields={'name': 'Recovery'},
            ),
        )
    )


def source_document(
    value: KpiDefinitionConfiguration | None = None,
) -> KpiDefinitionSourceDocument:
    return KpiDefinitionSourceDocument.create(
        configuration=value or configuration(),
        saved_by='source-user',
        saved_at_utc=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )


def test_validate_configuration_uses_domain_digest_and_summary() -> None:
    source = SourceStub()
    service = KpiDefinitionAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.validate_configuration(configuration())

    assert result.valid is True
    assert result.draft_revision == build_kpi_definition_digest(configuration())
    assert result.audit.actor == 'manager-user'
    assert result.audit.occurred_at_utc.tzinfo is UTC
    assert tuple((item.label, item.value) for item in result.summary) == (
        ('KPIs', '2'),
        ('Campos', '3'),
    )


def test_publish_configuration_writes_new_source_with_expected_revision() -> None:
    source = SourceStub()
    publisher = PublisherStub(source)
    service = KpiDefinitionAdministrationService(
        source=source,
        publisher=publisher,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.publish_configuration(
        configuration(),
        expected_source_revision=None,
    )

    assert result.published is True
    assert publisher.calls == 1
    assert source.document is not None
    assert source.document.revision == result.source_revision
    assert source.document.saved_by == 'manager-user'


def test_publish_configuration_skips_identical_content() -> None:
    current = source_document()
    source = SourceStub(current)
    publisher = PublisherStub(source)
    service = KpiDefinitionAdministrationService(
        source=source,
        publisher=publisher,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.publish_configuration(
        current.configuration,
        expected_source_revision=current.revision,
    )

    assert result.published is False
    assert result.source_revision == current.revision
    assert publisher.calls == 0


def test_publish_configuration_rejects_changed_source_revision() -> None:
    current = source_document()
    source = SourceStub(current)
    service = KpiDefinitionAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(
        KpiDefinitionSourceError,
        match='KPI definition source revision changed before publication',
    ):
        service.publish_configuration(
            current.configuration,
            expected_source_revision='stale',
        )


def test_projection_status_preserves_source_and_active_metadata() -> None:
    current = source_document()
    active = KpiDefinitionProjection.create(
        configuration=current.configuration,
        source_revision=current.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
    )
    workflow = KpiDefinitionProjectionWorkflow(
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


def test_project_creates_projection_for_expected_source() -> None:
    current = source_document()
    repository = ProjectionStub()
    workflow = KpiDefinitionProjectionWorkflow(
        source=SourceStub(current),
        projection=repository,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.project(current.revision)

    assert result.projected is True
    assert result.source_revision == current.revision
    assert repository.save_calls == 1
    assert repository.projection is not None
    assert repository.projection.source_revision == current.revision
    assert repository.projection.projected_by == 'manager-user'


def test_project_skips_already_synchronized_projection() -> None:
    current = source_document()
    active = KpiDefinitionProjection.create(
        configuration=current.configuration,
        source_revision=current.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
    )
    repository = ProjectionStub(active)
    workflow = KpiDefinitionProjectionWorkflow(
        source=SourceStub(current),
        projection=repository,
        audit_actor_provider=lambda: 'manager-user',
    )

    result = workflow.project(current.revision)

    assert result.projected is False
    assert result.projection_revision == active.revision
    assert result.audit.actor == 'projector'
    assert repository.save_calls == 0


def test_project_requires_existing_expected_source() -> None:
    workflow = KpiDefinitionProjectionWorkflow(
        source=SourceStub(),
        projection=ProjectionStub(),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(KpiDefinitionSourceError, match='KPI definition source does not exist'):
        workflow.project('expected')


def test_project_rejects_stale_source_revision() -> None:
    current = source_document()
    workflow = KpiDefinitionProjectionWorkflow(
        source=SourceStub(current),
        projection=ProjectionStub(),
        audit_actor_provider=lambda: 'manager-user',
    )

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='KPI definition source revision changed before projection',
    ):
        workflow.project('stale')
