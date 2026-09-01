from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAdministrationService,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionSourceDocument,
    KpiDefinitionSourceError,
)


class SourceStub:
    def __init__(self, *, current, history):
        self.current = current
        self.history = history
        self.requested_limit = None

    def load(self):
        return self.current

    def list_history(self, *, limit=20):
        self.requested_limit = limit
        return self.history[:limit]

    def load_revision(self, revision):
        return next(
            (item for item in self.history if item.revision == revision),
            None,
        )


class PublisherStub:
    def publish(self, document, *, expected_revision):
        raise AssertionError('Publisher must not be used by history reads')


class AuthorityStub:
    def load(self):
        return KpiDefinitionAuthorityCatalog(
            kpi_configuration_revision='kpi-config-r1',
            kpi_keys=('throughput',),
        )


def configuration(*, name: str) -> KpiDefinitionConfiguration:
    return KpiDefinitionConfiguration(
        (
            KpiDefinition(
                kpi_key='throughput',
                fields={'name': name},
            ),
        )
    )


def document(*, name: str, actor: str, hour: int) -> KpiDefinitionSourceDocument:
    return KpiDefinitionSourceDocument.create(
        configuration=configuration(name=name),
        saved_by=actor,
        saved_at_utc=datetime(2026, 9, 1, hour, 0, tzinfo=UTC),
    )


def service(source: SourceStub) -> KpiDefinitionAdministrationService:
    return KpiDefinitionAdministrationService(
        source=source,
        publisher=PublisherStub(),
        authority=AuthorityStub(),
        audit_actor_provider=lambda: 'manager-user',
    )


def test_list_history_delegates_limit_and_preserves_source_order() -> None:
    newest = document(name='Current', actor='current-user', hour=12)
    previous = document(name='Previous', actor='previous-user', hour=11)
    source = SourceStub(current=newest, history=(newest, previous))

    result = service(source).list_history(limit=1)

    assert result == (newest,)
    assert source.requested_limit == 1


def test_load_revision_configuration_recovers_historical_content() -> None:
    current = document(name='Current', actor='current-user', hour=12)
    previous = document(name='Previous', actor='previous-user', hour=11)
    source = SourceStub(current=current, history=(current, previous))

    recovered = service(source).load_revision_configuration(previous.revision)

    assert recovered == previous.configuration
    assert recovered != current.configuration


@pytest.mark.parametrize('revision', ['', '   ', 'missing'])
def test_load_revision_configuration_rejects_missing_revision(revision: str) -> None:
    current = document(name='Current', actor='current-user', hour=12)
    source = SourceStub(current=current, history=(current,))

    with pytest.raises(
        KpiDefinitionSourceError,
        match='revision does not exist',
    ):
        service(source).load_revision_configuration(revision)
