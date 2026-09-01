from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAdministrationService,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionCoverageStatus,
    KpiDefinitionProjection,
    KpiDefinitionProjectionError,
    KpiDefinitionProjectionWorkflow,
    KpiDefinitionSourceDocument,
    KpiDefinitionSourceError,
    KpiDefinitionValidationError,
    build_kpi_definition_digest,
)


class SourceStub:
    def __init__(self, document=None):
        self.document = document

    def load(self):
        return self.document


class PublisherStub:
    def __init__(self, source):
        self.source = source
        self.calls = 0

    def publish(self, document, *, expected_revision):
        current = self.source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_revision:
            raise RuntimeError('source conflict')
        self.calls += 1
        self.source.document = document


class ProjectionStub:
    def __init__(self, projection=None):
        self.projection = projection
        self.save_calls = 0

    def load(self):
        return self.projection

    def save(self, projection):
        self.save_calls += 1
        self.projection = projection
        return projection

    def health_check(self):
        return True


class AuthorityStub:
    def __init__(self, value):
        self.value = value

    def load(self):
        return self.value


def configuration(*keys: str) -> KpiDefinitionConfiguration:
    selected = keys or ('throughput', 'recovery')
    return KpiDefinitionConfiguration(
        tuple(
            KpiDefinition(
                kpi_key=key,
                fields={'name': key.title()},
            )
            for key in selected
        )
    )


def source_document(value=None):
    return KpiDefinitionSourceDocument.create(
        configuration=value or configuration(),
        saved_by='source-user',
        saved_at_utc=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )


def authority(
    *keys: str,
    revision='kpi-config-r1',
) -> KpiDefinitionAuthorityCatalog:
    return KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision=revision,
        kpi_keys=tuple(keys or ('throughput', 'recovery')),
    )


def administration(source, authority_value):
    return KpiDefinitionAdministrationService(
        source=source,
        publisher=PublisherStub(source),
        authority=AuthorityStub(authority_value),
        audit_actor_provider=lambda: 'manager-user',
    )


def workflow(source, projection, authority_value):
    return KpiDefinitionProjectionWorkflow(
        source=source,
        projection=projection,
        authority=AuthorityStub(authority_value),
        audit_actor_provider=lambda: 'manager-user',
    )


def test_validation_uses_kpi_configuration_as_authority() -> None:
    source = SourceStub()
    service = administration(source, authority('throughput', 'recovery'))

    result = service.validate_configuration(configuration('throughput'))

    assert result.valid is True
    assert result.draft_revision == build_kpi_definition_digest(configuration('throughput'))
    assert result.kpi_configuration_revision == 'kpi-config-r1'
    assert tuple(issue.code for issue in result.issues) == ('kpi_definition.missing',)
    assert result.issues[0].level == 'warning'


def test_validation_without_kpi_configuration_authority_is_invalid() -> None:
    source = SourceStub()
    result = administration(source, None).validate_configuration(configuration('throughput'))

    assert result.valid is False
    assert result.issues[0].code == 'kpi_definition.authority.missing'


def test_orphan_definition_is_error_and_blocks_publication() -> None:
    source = SourceStub()
    service = administration(source, authority('throughput'))
    draft = configuration('throughput', 'orphan')

    result = service.validate_configuration(draft)

    assert result.valid is False
    assert result.issues[0].code == 'kpi_definition.orphan'
    with pytest.raises(KpiDefinitionValidationError):
        service.publish_configuration(
            draft,
            expected_source_revision=None,
        )


def test_missing_definition_is_warning_and_does_not_block_publication() -> None:
    source = SourceStub()
    publisher = PublisherStub(source)
    service = KpiDefinitionAdministrationService(
        source=source,
        publisher=publisher,
        authority=AuthorityStub(authority('throughput', 'recovery')),
        audit_actor_provider=lambda: 'manager-user',
    )

    result = service.publish_configuration(
        configuration('throughput'),
        expected_source_revision=None,
    )

    assert result.published is True
    assert publisher.calls == 1
    assert result.kpi_configuration_revision == 'kpi-config-r1'


def test_publish_keeps_source_cas() -> None:
    current = source_document()
    source = SourceStub(current)
    service = administration(source, authority())

    with pytest.raises(
        KpiDefinitionSourceError,
        match='source revision changed before publication',
    ):
        service.publish_configuration(
            current.configuration,
            expected_source_revision='stale',
        )


def test_projection_builds_virtual_missing_coverage() -> None:
    current = source_document(configuration('throughput'))
    repository = ProjectionStub()
    result = workflow(
        SourceStub(current),
        repository,
        authority('throughput', 'recovery'),
    ).project(current.revision)

    assert result.projected is True
    assert repository.projection is not None
    assert repository.projection.missing_kpi_keys == ('recovery',)
    missing = repository.projection.coverage_item('recovery')
    assert missing is not None
    assert missing.status is KpiDefinitionCoverageStatus.MISSING


def test_projection_is_noop_only_when_source_and_authority_match() -> None:
    current = source_document(configuration('throughput'))
    first_authority = authority('throughput', revision='kpi-config-r1')
    active = KpiDefinitionProjection.create(
        configuration=current.configuration,
        source_revision=current.revision,
        authority=first_authority,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
    )
    repository = ProjectionStub(active)

    same = workflow(
        SourceStub(current),
        repository,
        first_authority,
    ).project(current.revision)

    assert same.projected is False
    assert repository.save_calls == 0


def test_authority_revision_change_reprojects_unchanged_definition_source() -> None:
    current = source_document(configuration('throughput'))
    old_authority = authority('throughput', revision='kpi-config-r1')
    active = KpiDefinitionProjection.create(
        configuration=current.configuration,
        source_revision=current.revision,
        authority=old_authority,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
    )
    repository = ProjectionStub(active)
    new_authority = authority(
        'throughput',
        'recovery',
        revision='kpi-config-r2',
    )

    result = workflow(
        SourceStub(current),
        repository,
        new_authority,
    ).project(current.revision)

    assert result.projected is True
    assert result.projection_revision != active.revision
    assert repository.projection is not None
    assert repository.projection.missing_kpi_keys == ('recovery',)


def test_projection_rejects_orphan_after_kpi_removed() -> None:
    current = source_document(configuration('throughput', 'recovery'))
    repository = ProjectionStub()

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='not valid for projection',
    ):
        workflow(
            SourceStub(current),
            repository,
            authority('throughput', revision='kpi-config-r2'),
        ).project(current.revision)

    assert repository.save_calls == 0


def test_projection_requires_existing_expected_source() -> None:
    with pytest.raises(
        KpiDefinitionSourceError,
        match='source does not exist',
    ):
        workflow(
            SourceStub(),
            ProjectionStub(),
            authority(),
        ).project('expected')
