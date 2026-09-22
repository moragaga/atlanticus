import ada_command_center.domain.alarms as alarms


def test_version() -> None:
    assert alarms.__version__ == '1.0.0'


def test_public_api_contains_authored_alarm_domain() -> None:
    expected = {
        'AlarmColor',
        'AlarmConfiguration',
        'AlarmConfigurationValidationError',
        'AlarmDeactivationDefinition',
        'AlarmDefinition',
        'AlarmEscalationDefinition',
        'AlarmEscalationStepDefinition',
        'AlarmIdentity',
        'AlarmKind',
        'AlarmVisualSubcomponentTarget',
        'AlarmVisualTarget',
        'BusinessCategory',
        'Criticality',
        'MessageDeactivationDefinition',
        'MessageDefinition',
        'MessageScope',
        'OperationalArea',
        'ProcessAlarmProjectionMode',
        'ReappearanceDefinition',
        'VisibilityMode',
    }
    assert expected <= set(alarms.__all__)
