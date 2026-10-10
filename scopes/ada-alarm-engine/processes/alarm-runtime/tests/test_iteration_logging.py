from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.processes.alarm_runtime.composition import _notable_iteration
from ada.processes.alarm_runtime.job import AlarmRuntimeConfigurationOutcome


def _result(*, outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED, groups=(), incidents=()):
    return SimpleNamespace(
        outcome=outcome,
        lifecycle=SimpleNamespace(groups=groups, technical_incident_changes=incidents),
    )


def _group(**changes):
    fields = dict(
        has_lifecycle_change=False,
        management_action_results=(),
        deactivation_request_results=(),
        deactivation_decision_results=(),
        cascade_suppressions=(),
    )
    fields.update(changes)
    return SimpleNamespace(adoption_decision=None, decision=SimpleNamespace(**fields))


def test_unchanged_evaluation_without_effects_does_not_request_summary():
    assert not _notable_iteration(_result(groups=(_group(),)))


@pytest.mark.parametrize(
    'outcome',
    [
        AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED,
        AlarmRuntimeConfigurationOutcome.ADOPTED,
        AlarmRuntimeConfigurationOutcome.REJECTED,
        AlarmRuntimeConfigurationOutcome.WAITING,
    ],
)
def test_non_routine_outcomes_request_summary(outcome):
    assert _notable_iteration(_result(outcome=outcome))


@pytest.mark.parametrize(
    'changes',
    [
        {'has_lifecycle_change': True},
        {'management_action_results': (object(),)},
        {'deactivation_request_results': (object(),)},
        {'deactivation_decision_results': (object(),)},
        {'cascade_suppressions': (object(),)},
    ],
)
def test_significant_group_changes_request_summary(changes):
    assert _notable_iteration(_result(groups=(_group(**changes),)))


def test_technical_incident_change_requests_summary():
    assert _notable_iteration(_result(incidents=(object(),)))
