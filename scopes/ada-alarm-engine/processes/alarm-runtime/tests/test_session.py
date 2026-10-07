import pytest

from ada.processes.alarm_runtime import (
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)
from ada.processes.alarm_runtime.errors import AlarmExecutionSessionError

from .support import engine_configuration, registry


def test_session_binds_planned_alarm_to_registered_evaluator() -> None:
    configuration = engine_configuration()
    session = build_alarm_execution_session(
        configuration=configuration,
        evaluator_registry=registry(),
    )
    assert session.configuration is configuration
    assert session.resolution_key == configuration.resolution_key
    assert session.planned_alarms == configuration.planned_alarms
    assert len(session.entries) == 1
    assert session.entries[0].parameters == {'limit': 10.0}


def test_session_rejects_unregistered_evaluator() -> None:
    with pytest.raises(AlarmExecutionSessionError, match='evaluator contract is not registered'):
        build_alarm_execution_session(
            configuration=engine_configuration(),
            evaluator_registry=AlarmEvaluatorRegistry(contracts=()),
        )


def test_registry_is_scoped_by_family_and_evaluator_key() -> None:
    configuration = engine_configuration()
    plan = configuration.planned_alarms[0]
    resolved = registry().resolve(plan)
    assert resolved.key == ('mill', 'threshold')
