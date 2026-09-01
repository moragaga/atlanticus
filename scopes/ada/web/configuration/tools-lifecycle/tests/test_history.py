from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.configuration.tools_lifecycle import (
    ToolAdministrationService,
    ToolConfigurationSourceSnapshot,
    ToolLifecycleSourceError,
)

from .helpers import valid_configuration


class SourceStub:
    def __init__(
        self,
        *,
        current: ToolConfigurationSourceSnapshot | None,
        history: tuple[ToolConfigurationSourceSnapshot, ...],
    ) -> None:
        self.current = current
        self.history = history
        self.requested_limit: int | None = None

    def load(self) -> ToolConfigurationSourceSnapshot | None:
        return self.current

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ToolConfigurationSourceSnapshot, ...]:
        self.requested_limit = limit
        return self.history[:limit]

    def load_revision(self, revision: str) -> ToolConfigurationSourceSnapshot | None:
        return next((item for item in self.history if item.revision == revision), None)


class PublisherStub:
    def publish(
        self,
        document: ToolConfigurationSourceSnapshot,
        *,
        expected_revision: str | None,
    ) -> None:
        raise AssertionError('Publisher must not be used by history reads')


def snapshot(
    *,
    display_name: str,
    actor: str,
    hour: int,
) -> ToolConfigurationSourceSnapshot:
    base = valid_configuration()
    configuration = type(base)(
        tool_key=base.tool_key,
        display_name=display_name,
        kind=base.kind,
        source_consumption=base.source_consumption,
        source_operational_participation=base.source_operational_participation,
        structure=base.structure,
    )
    return ToolConfigurationSourceSnapshot.create(
        configuration=configuration,
        saved_by=actor,
        saved_at_utc=datetime(2026, 9, 1, hour, 0, tzinfo=UTC),
    )


def service(source: SourceStub) -> ToolAdministrationService:
    return ToolAdministrationService(
        source=source,
        publisher=PublisherStub(),
        audit_actor_provider=lambda: 'manager-user',
    )


def test_list_history_delegates_limit_and_preserves_source_order() -> None:
    newest = snapshot(display_name='Current', actor='current-user', hour=12)
    previous = snapshot(display_name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=newest,
        history=(newest, previous),
    )

    result = service(source).list_history(limit=1)

    assert result == (newest,)
    assert source.requested_limit == 1


def test_load_revision_configuration_recovers_historical_content() -> None:
    current = snapshot(display_name='Current', actor='current-user', hour=12)
    previous = snapshot(display_name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=current,
        history=(current, previous),
    )

    recovered = service(source).load_revision_configuration(previous.revision)

    assert recovered == previous.configuration
    assert recovered != current.configuration


def test_load_revision_configuration_normalizes_revision() -> None:
    previous = snapshot(display_name='Previous', actor='previous-user', hour=11)
    source = SourceStub(
        current=previous,
        history=(previous,),
    )

    recovered = service(source).load_revision_configuration(f'  {previous.revision}  ')

    assert recovered == previous.configuration


@pytest.mark.parametrize('revision', ['', '   ', 'missing'])
def test_load_revision_configuration_rejects_missing_revision(revision: str) -> None:
    current = snapshot(display_name='Current', actor='current-user', hour=12)
    source = SourceStub(
        current=current,
        history=(current,),
    )

    with pytest.raises(
        ToolLifecycleSourceError,
        match='Tool revision does not exist',
    ):
        service(source).load_revision_configuration(revision)
