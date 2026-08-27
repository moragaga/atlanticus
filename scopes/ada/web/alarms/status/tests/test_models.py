import pytest

from ada.web.alarms.status import AlarmStatusDefinitionError, AlarmStatusState


def test_alarm_status_accepts_zero_and_positive_counts() -> None:
    state = AlarmStatusState(active_count=3, managed_count=0)

    assert state.active_count == 3
    assert state.managed_count == 0


def test_alarm_status_rejects_negative_counts() -> None:
    with pytest.raises(AlarmStatusDefinitionError, match='cannot be negative'):
        AlarmStatusState(active_count=-1, managed_count=0)
