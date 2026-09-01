from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationAdministrationService,
    KpiConfigurationBinding,
    KpiConfigurationProjectionError,
    KpiConfigurationProjectionWorkflow,
    KpiConfigurationSourceDocument,
    KpiConfigurationSourceError,
    KpiDestination,
    KpiDestinationCatalog,
)


class Source:
    def __init__(self, document=None, history=()):
        self.document = document
        self.history = tuple(history)

    def load(self):
        return self.document

    def list_history(self, *, limit=20):
        return self.history[:limit]

    def load_revision(self, revision):
        return next(
            (item for item in self.history if item.revision == revision),
            None,
        )


class Publisher:
    def __init__(self, source):
        self.source = source
        self.calls = 0

    def publish(self, document, *, expected_revision):
        current = self.source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_revision:
            raise RuntimeError('conflict')
        self.calls += 1
        self.source.document = document


class Destinations:
    def __init__(self, value):
        self.value = value

    def load(self):
        return self.value


class ProjectionRepository:
    def __init__(self):
        self.value = None
        self.calls = 0

    def load(self):
        return self.value

    def save(self, projection):
        self.calls += 1
        self.value = projection
        return projection

    def health_check(self):
        return True


def configuration(destination='crusher'):
    return KpiConfiguration(
        (
            KpiConfigurationBinding(
                kpi_key='throughput',
                destination_keys=(destination,),
                series_enabled=True,
                series_hours=4,
            ),
        )
    )


def catalog(revision='tool-r1'):
    return KpiDestinationCatalog(
        tool_projection_revision=revision,
        destinations=(
            KpiDestination('global_indicators', 'Global Indicators'),
            KpiDestination('time_status', 'Time Status'),
            KpiDestination('crusher', 'Chancado'),
        ),
    )


def test_validation_requires_tool_projection() -> None:
    source = Source()
    service = KpiConfigurationAdministrationService(
        source=source,
        publisher=Publisher(source),
        destinations=Destinations(None),
        audit_actor_provider=lambda: 'admin',
    )
    result = service.validate_configuration(configuration())
    assert result.valid is False
    assert result.issues[0].code == 'kpi.tool_projection.missing'


def test_validation_rejects_destination_removed_from_tool() -> None:
    source = Source()
    service = KpiConfigurationAdministrationService(
        source=source,
        publisher=Publisher(source),
        destinations=Destinations(catalog()),
        audit_actor_provider=lambda: 'admin',
    )
    result = service.validate_configuration(configuration('unknown'))
    assert result.valid is False
    assert result.issues[0].code == 'kpi.destination.unavailable'


def test_publish_uses_cas_and_noop_avoids_second_write() -> None:
    source = Source()
    publisher = Publisher(source)
    service = KpiConfigurationAdministrationService(
        source=source,
        publisher=publisher,
        destinations=Destinations(catalog()),
        audit_actor_provider=lambda: 'admin',
    )
    first = service.publish_configuration(
        configuration(),
        expected_source_revision=None,
    )
    second = service.publish_configuration(
        configuration(),
        expected_source_revision=first.source_revision,
    )
    assert first.published is True
    assert second.published is False
    assert publisher.calls == 1


def test_history_recovery_is_read_only() -> None:
    historical = KpiConfigurationSourceDocument.create(
        configuration=configuration(),
        saved_by='admin',
        saved_at_utc=datetime(2026, 8, 31, tzinfo=UTC),
    )
    source = Source(history=(historical,))
    publisher = Publisher(source)
    service = KpiConfigurationAdministrationService(
        source=source,
        publisher=publisher,
        destinations=Destinations(catalog()),
        audit_actor_provider=lambda: 'admin',
    )
    assert service.load_revision_configuration(historical.revision) == historical.configuration
    assert publisher.calls == 0


def test_unknown_history_revision_fails() -> None:
    source = Source()
    service = KpiConfigurationAdministrationService(
        source=source,
        publisher=Publisher(source),
        destinations=Destinations(catalog()),
        audit_actor_provider=lambda: 'admin',
    )
    with pytest.raises(KpiConfigurationSourceError):
        service.load_revision_configuration('missing')


def test_projection_reprojects_when_tool_revision_changes() -> None:
    document = KpiConfigurationSourceDocument.create(
        configuration=configuration(),
        saved_by='admin',
        saved_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )
    source = Source(document)
    repository = ProjectionRepository()
    destinations = Destinations(catalog('tool-r1'))
    workflow = KpiConfigurationProjectionWorkflow(
        source=source,
        projection=repository,
        destinations=destinations,
        audit_actor_provider=lambda: 'admin',
    )
    first = workflow.project(document.revision)
    same = workflow.project(document.revision)
    destinations.value = catalog('tool-r2')
    second = workflow.project(document.revision)

    assert first.projected is True
    assert same.projected is False
    assert second.projected is True
    assert first.projection_revision != second.projection_revision
    assert repository.calls == 2


def test_projection_rejects_invalid_current_tool_destinations() -> None:
    document = KpiConfigurationSourceDocument.create(
        configuration=configuration(),
        saved_by='admin',
        saved_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )
    source = Source(document)
    repository = ProjectionRepository()
    destinations = Destinations(
        KpiDestinationCatalog(
            tool_projection_revision='tool-r2',
            destinations=(
                KpiDestination('global_indicators', 'Global Indicators'),
                KpiDestination('time_status', 'Time Status'),
            ),
        )
    )
    workflow = KpiConfigurationProjectionWorkflow(
        source=source,
        projection=repository,
        destinations=destinations,
        audit_actor_provider=lambda: 'admin',
    )
    with pytest.raises(KpiConfigurationProjectionError):
        workflow.project(document.revision)
    assert repository.calls == 0
