import pytest

from ada_command_center.alarms.core import AlarmIdentity, AlarmKind, MessageScope
from ada_command_center.web.alarms.configuration import (
    AlarmConfiguration,
    AlarmConfigurationValidationError,
)

from .helpers import configuration, message, rule


def test_alarm_configuration_document_round_trips_core_contracts() -> None:
    value = configuration()

    decoded = AlarmConfiguration.from_document(value.to_document())

    assert decoded == value
    assert decoded.rules[0].parameters == value.rules[0].parameters


def test_alarm_configuration_requires_unique_alarm_identity() -> None:
    first = rule('alarm-1', rule_name='first')
    duplicate = rule('alarm-1', rule_name='second', priority_order=2)

    with pytest.raises(
        AlarmConfigurationValidationError, match='Duplicate Alarm Configuration identity'
    ):
        AlarmConfiguration(rules=(first, duplicate), messages=(message(),))


def test_alarm_configuration_requires_rule_name_unique_within_family() -> None:
    first = rule('alarm-1', rule_name='shared')
    second = rule('alarm-2', rule_name='shared', priority_order=2)

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='rule_name must be unique within family',
    ):
        AlarmConfiguration(rules=(first, second), messages=(message(),))


def test_alarm_configuration_allows_rule_name_reuse_across_families() -> None:
    first = rule('alarm-1', family_key='family-a', rule_name='shared')
    second = rule(
        'alarm-1',
        family_key='family-b',
        rule_name='shared',
        priority_group='group-b',
        message_keys=(),
    )

    value = AlarmConfiguration(rules=(first, second), messages=(message(),))

    assert len(value.rules) == 2


def test_alarm_configuration_requires_unique_priority_order_within_group() -> None:
    first = rule('alarm-1', priority_order=1)
    second = rule('alarm-2', priority_order=1)

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='priority_order must be unique within priority_group',
    ):
        AlarmConfiguration(rules=(first, second), messages=(message(),))


def test_alarm_configuration_requires_impact_before_risk() -> None:
    risk = rule('risk', kind=AlarmKind.RISK, priority_order=1)
    impact = rule('impact', kind=AlarmKind.IMPACT, priority_order=2)

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='All IMPACT priority orders must precede RISK',
    ):
        AlarmConfiguration(rules=(risk, impact), messages=(message(),))


def test_alarm_configuration_requires_global_message_key_identity() -> None:
    global_message = message('shared')
    family_message = message(
        'shared',
        scope=MessageScope.FAMILY,
        family_key='family-a',
    )

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='Duplicate Alarm Configuration message_key',
    ):
        AlarmConfiguration(rules=(), messages=(global_message, family_message))


def test_alarm_configuration_requires_referenced_message_to_exist() -> None:
    value = rule(message_keys=('missing',))

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='references unknown message_key',
    ):
        AlarmConfiguration(rules=(value,), messages=())


def test_alarm_configuration_restricts_family_message_to_same_family() -> None:
    value = rule(message_keys=('family-message',))
    foreign = message(
        'family-message',
        scope=MessageScope.FAMILY,
        family_key='family-b',
    )

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='only GLOBAL messages or messages from its family',
    ):
        AlarmConfiguration(rules=(value,), messages=(foreign,))


def test_alarm_configuration_keeps_inactive_message_reference_intrinsically_valid() -> None:
    value = rule(message_keys=('inactive-message',))
    inactive = message('inactive-message', is_active=False)

    configuration = AlarmConfiguration(rules=(value,), messages=(inactive,))

    assert configuration.messages[0].is_active is False


def test_alarm_configuration_requires_special_condition_to_exist() -> None:
    missing = AlarmIdentity(family_key='family-a', alarm_key='special')
    value = rule(special_conditions=(missing,))

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='unknown special condition',
    ):
        AlarmConfiguration(rules=(value,), messages=(message(),))


def test_alarm_configuration_requires_special_condition_flag() -> None:
    target = rule('special', priority_order=2)
    value = rule(
        'alarm-1',
        special_conditions=(target.identity,),
        priority_order=1,
    )

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='must target a special condition',
    ):
        AlarmConfiguration(rules=(value, target), messages=(message(),))


def test_alarm_configuration_requires_special_condition_same_family_and_group() -> None:
    target = rule(
        'special',
        family_key='family-b',
        priority_group='group-b',
        is_special_condition=True,
        message_keys=(),
    )
    value = rule('alarm-1', special_conditions=(target.identity,))

    with pytest.raises(
        AlarmConfigurationValidationError,
        match='must belong to the same family',
    ):
        AlarmConfiguration(rules=(value, target), messages=(message(),))
