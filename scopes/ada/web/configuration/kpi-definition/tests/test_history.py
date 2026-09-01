from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAdministrationService,
    KpiDefinitionConfiguration,
    KpiDefinitionSourceDocument,
    KpiDefinitionSourceError,
)


class SourceStub:
    def __init__(
        self,
        *,
        current: KpiDefinitionSourceDocument | None,
        history: tuple[KpiDefinitionSourceDocument, ...],
    ) -> None:
        self.current = current
        self.history = history
        self.requested_limit: int | None = None

    def load(self) -> KpiDefinitionSourceDocument | None:
        return self.current

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiDefinitionSourceDocument, ...]:
        self.requested_limit = limit
        return self.history[:limit]

    def load_revision(self, revision: str) -> KpiDefinitionSourceDocument | None:
        return next((item for item in self.history if item.revision == revision), None)


class PublisherStub:
    def publish(
        self,
        document: KpiDefinitionSourceDocument,
        *,
        expected_revision: str | None,
    ) -> None:
        raise AssertionError('Publisher must not be used by history reads')


def configuration(*, name: str) -> KpiDefinitionConfiguration:
    return KpiDefinitionConfiguration(
        definitions=(
            KpiDefinition(
                kpi_key='throughput',
                fields={'name': name},
            ),
        )
    )


def document(
    *,
    name: str,
    actor: str,
    hour: int,
) -> KpiDefinitionSourceDocument:
    return KpiDefinitionSourceDocument.create(
        configuration=configuration(name=name),
        saved_by=actor,
        saved_at_utc=datetime(2026, 9, 1, hour, 0, tzinfo=UTC),
    )


def service(source: SourceStub) -> KpiDefinitionAdministrationService:
    return KpiDefinitionAdministrationService(
        source=source,
        publisher=PublisherStub(),
        audit_actor_provider=lambda: 'manager-user',
    )


def test_list_history_delegates_limit_and_preserves_source_order() -> None:
    newest = document(name='Current', actor='current-user', hour=12)
    previous = document(name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=newest,
        history=(newest, previous),
    )

    result = service(source).list_history(limit=1)

    assert result == (newest,)
    assert source.requested_limit == 1


def test_load_revision_configuration_recovers_historical_content() -> None:
    current = document(name='Current', actor='current-user', hour=12)
    previous = document(name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=current,
        history=(current, previous),
    )

    recovered = service(source).load_revision_configuration(previous.revision)

    assert recovered == previous.configuration
    assert recovered != current.configuration


def test_load_revision_configuration_normalizes_revision() -> None:
    previous = document(name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=previous,
        history=(previous,),
    )

    recovered = service(source).load_revision_configuration(f'  {previous.revision}  ')

    assert recovered == previous.configuration


@pytest.mark.parametrize('revision', ['', '   ', 'missing'])
def test_load_revision_configuration_rejects_missing_revision(revision: str) -> None:
    current = document(name='Current', actor='current-user', hour=12)
    source = SourceStub(
        current=current,
        history=(current,),
    )

    with pytest.raises(
        KpiDefinitionSourceError,
        match='KPI definition revision does not exist',
    ):
        service(source).load_revision_configuration(revision)
