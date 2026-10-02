# Cada ciclo incluye todas las fuentes.
# El orden prioriza la última sincronización realizada por Atlanticus.
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from atlanticus.data_producers.core import SourceScopeProvider
from atlanticus.data_producers.sql.models import (
    SqlExecutionPlan,
    SqlLoadStrategy,
    SqlSourceDefinition,
    SqlSourcePlan,
)
from atlanticus.data_producers.sql.producer_state import SqlProducerState
from atlanticus.runtime import JobRuntimeContext


class SqlDataProducerPlanner:
    def __init__(
        self,
        *,
        producer_state: SqlProducerState,
        scope_provider: SourceScopeProvider | None = None,
    ) -> None:
        if not isinstance(producer_state, SqlProducerState):
            raise TypeError('producer_state must be a SqlProducerState')
        if scope_provider is not None and not isinstance(scope_provider, SourceScopeProvider):
            raise TypeError('scope_provider must implement SourceScopeProvider')
        self._producer_state = producer_state
        self._scope_provider = scope_provider

    def capture(
        self,
        definitions: Sequence[SqlSourceDefinition],
        *,
        captured_at_utc: datetime | None = None,
        context: JobRuntimeContext | None = None,
    ) -> SqlExecutionPlan:
        if context is not None:
            context.raise_if_cancelled()
        normalized = tuple(definitions)
        captured_at = _normalize_utc(captured_at_utc or datetime.now(UTC))
        uses_scope = any(
            definition.load_strategy is SqlLoadStrategy.SCOPED for definition in normalized
        )
        scope = None
        if uses_scope:
            if self._scope_provider is None:
                raise ValueError('scope_provider is required for scoped SQL sources')
            scope = self._scope_provider.capture(captured_at_utc=captured_at)
            if context is not None:
                context.raise_if_cancelled()
        candidates: list[tuple[datetime | None, int, SqlSourcePlan]] = []
        for catalog_index, definition in enumerate(normalized):
            state = self._producer_state.source_state(definition.source_key)
            source_scope = scope if definition.load_strategy is SqlLoadStrategy.SCOPED else None
            candidates.append(
                (
                    state.last_synced_at_utc,
                    catalog_index,
                    SqlSourcePlan(
                        definition=definition,
                        scope=source_scope,
                    ),
                )
            )
        candidates.sort(key=_candidate_order)
        return SqlExecutionPlan(
            captured_at_utc=captured_at,
            sources=tuple(candidate[2] for candidate in candidates),
        )


def _normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('captured_at_utc must be timezone-aware')
    return value.astimezone(UTC)


def _candidate_order(
    candidate: tuple[datetime | None, int, SqlSourcePlan],
) -> tuple[datetime, int]:
    last_synced_at_utc, catalog_index, _plan = candidate
    return (last_synced_at_utc or datetime.min.replace(tzinfo=UTC), catalog_index)
