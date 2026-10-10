from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ada.alarms.core import AlarmStatus, EvaluationContext
from ada.alarms.materialization import engine_from_document
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.session import build_alarm_execution_session
from stress.run_synthetic import (
    build_registry,
    make_evaluator,
    synthetic_decision,
    synthetic_phase,
    validate_fixtures,
)


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'fixtures'


def test_fixture_integrity_and_three_registered_evaluators() -> None:
    ready, document = validate_fixtures(_fixture_root())
    assert ready['result_id'].startswith('alarm-materialization-')
    engine = engine_from_document(document)
    registry = build_registry(
        engine=engine,
        seed=20261008,
        started_at_utc=datetime(2026, 10, 9, tzinfo=UTC),
        random_seconds=210,
        hold_seconds=335,
    )
    session = build_alarm_execution_session(configuration=engine, evaluator_registry=registry)
    assert len(session.entries) == 3
    assert not session.data_plan.views
    assert all(not entry.inputs for entry in session.entries)


def test_synthetic_results_are_reproducible_and_valid() -> None:
    start = datetime(2026, 10, 9, tzinfo=UTC)
    evaluator = make_evaluator(seed=42, started_at_utc=start, random_seconds=210, hold_seconds=335)
    from datetime import timedelta

    identity = AlarmIdentity('MP10', 'alarm-ec7667c94931')
    for tick in (0, 1, 2, 209, 210, 510, 544, 545, 580):
        ctx = EvaluationContext(
            alarm_identity=identity, now=start + timedelta(seconds=tick), parameters={}, data=None
        )
        value = evaluator(ctx)
        expected = tick in range(210, 545) or synthetic_decision(
            seed=42, tick=tick, family_key='MP10', alarm_key=identity.alarm_key
        )
        assert value.status is (AlarmStatus.ACTIVE if expected else AlarmStatus.INACTIVE)
        assert value.evidence_snapshot is not None
        assert value.evidence_snapshot.payload['synthetic'] is True
        assert evaluator(ctx) == value


def test_phase_boundaries() -> None:
    assert synthetic_phase(209, random_seconds=210, hold_seconds=335) == 'RANDOM_INITIAL'
    assert synthetic_phase(210, random_seconds=210, hold_seconds=335) == 'HOLD_ACTIVE'
    assert synthetic_phase(544, random_seconds=210, hold_seconds=335) == 'HOLD_ACTIVE'
    assert synthetic_phase(545, random_seconds=210, hold_seconds=335) == 'RANDOM_FINAL'
