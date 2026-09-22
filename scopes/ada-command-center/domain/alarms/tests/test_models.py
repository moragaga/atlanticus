import pytest

from ada_command_center.domain.alarms import AlarmIdentity, AlarmKind, Criticality


def test_identity_is_stable_pair() -> None:
    value = AlarmIdentity(family_key='ph', alarm_key='high')
    assert value.canonical_key == 'ph/high'


def test_identity_rejects_empty_keys() -> None:
    with pytest.raises(ValueError, match='family_key'):
        AlarmIdentity(family_key='', alarm_key='high')


def test_alarm_kind_values_are_stable() -> None:
    assert {value.value for value in AlarmKind} == {'RISK', 'IMPACT'}


def test_criticality_values_are_stable() -> None:
    assert {value.value for value in Criticality} == {'C1', 'C2', 'C3'}
