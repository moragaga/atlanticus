from dataclasses import replace
from datetime import UTC, datetime

from atlanticus.data_producers.core import SourceScope, SourceScopeItem
from atlanticus.data_producers.sql import SqlDataProducerPlanner, SqlProducerState, SqlSourceState


class _State(SqlProducerState):
    def __init__(self, values):
        self.values = values

    def source_state(self, source_key):
        return self.values.get(source_key, SqlSourceState(source_key=source_key))


class _ScopeProvider:
    def __init__(self):
        self.calls = 0

    def capture(self, *, captured_at_utc):
        self.calls += 1
        return SourceScope(
            token='1|2',
            items=(
                SourceScopeItem(value=1, partition={'year': '2026', 'window': '1'}),
                SourceScopeItem(value=2, partition={'year': '2026', 'window': '2'}),
            ),
        )


def test_planner_captures_scope_once_and_always_plans_scoped_source(scoped_definition) -> None:
    scope_provider = _ScopeProvider()
    planner = SqlDataProducerPlanner(
        producer_state=_State(
            {
                'source_scoped': SqlSourceState(
                    source_key='source_scoped',
                    source_scope_token='1|2',
                    last_synced_at_utc=datetime(2026, 10, 2, 11, 59, tzinfo=UTC),
                )
            }
        ),
        scope_provider=scope_provider,
    )

    plan = planner.capture(
        (scoped_definition,),
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )

    assert scope_provider.calls == 1
    assert len(plan.sources) == 1
    assert plan.sources[0].scope_token == '1|2'
    assert plan.sources[0].scope.values == (1, 2)


def test_planner_does_not_require_scope_provider_for_snapshot(snapshot_definition) -> None:
    planner = SqlDataProducerPlanner(producer_state=_State({}))

    plan = planner.capture(
        (snapshot_definition,),
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )

    assert plan.sources[0].scope is None


def test_planner_prioritizes_least_recently_synced_source(snapshot_definition) -> None:
    recent_definition = replace(
        snapshot_definition,
        source_key='source_recent',
        source_table='dbo.source_recent',
    )
    overdue_definition = replace(
        snapshot_definition,
        source_key='source_overdue',
        source_table='dbo.source_overdue',
    )
    planner = SqlDataProducerPlanner(
        producer_state=_State(
            {
                'source_recent': SqlSourceState(
                    source_key='source_recent',
                    last_synced_at_utc=datetime(2026, 10, 2, 11, 59, tzinfo=UTC),
                ),
                'source_overdue': SqlSourceState(
                    source_key='source_overdue',
                    last_synced_at_utc=datetime(2026, 10, 2, 11, 0, tzinfo=UTC),
                ),
            }
        )
    )

    plan = planner.capture(
        (recent_definition, overdue_definition),
        captured_at_utc=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )

    assert tuple(item.definition.source_key for item in plan.sources) == (
        'source_overdue',
        'source_recent',
    )
