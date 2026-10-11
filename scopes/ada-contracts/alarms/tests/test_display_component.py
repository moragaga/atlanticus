from dataclasses import replace

import pytest

from ada.contracts.alarms import (
    AlarmConfiguration,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
)

from .helpers import configuration


def test_display_component_is_a_single_selected_component() -> None:
    target = AlarmVisualTarget(
        tool_key='integrated-operations',
        component_keys=('general-mine', 'haulage', 'crushing'),
        display_component_key='general-mine',
        subcomponents=(AlarmVisualSubcomponentTarget('haulage', 'conveyor'),),
    )
    assert target.display_component_key == 'general-mine'
    assert target.component_keys == ('general-mine', 'haulage', 'crushing')
    assert target.subcomponents[0].owner_component_key == 'haulage'


@pytest.mark.parametrize('key', ['missing', '', ' '])
def test_display_component_must_be_selected_and_nonempty(key: str) -> None:
    with pytest.raises((TypeError, ValueError), match='display_component_key'):
        AlarmVisualTarget(
            tool_key='integrated-operations',
            component_keys=('general-mine', 'haulage'),
            display_component_key=key,
        )


def test_configuration_roundtrips_display_location_without_replacing_affectations() -> None:
    original = configuration()
    target = AlarmVisualTarget(
        tool_key='tool-a',
        component_keys=('general-mine', 'haulage'),
        display_component_key='general-mine',
        subcomponents=(AlarmVisualSubcomponentTarget('haulage', 'conveyor'),),
    )
    modified = replace(original.rules[0], visual_targets=(target,))
    value = AlarmConfiguration(rules=(modified,), messages=original.messages)
    document = value.to_document()
    encoded = document['rules'][0]['visual_targets'][0]
    assert encoded['display_component_key'] == 'general-mine'
    assert encoded['component_keys'] == ['general-mine', 'haulage']
    assert AlarmConfiguration.from_document(document) == value


def test_absent_optional_display_component_is_none_for_process_targets() -> None:
    document = configuration().to_document()
    del document['rules'][0]['visual_targets'][0]['display_component_key']
    decoded = AlarmConfiguration.from_document(document)
    assert decoded.rules[0].visual_targets[0].display_component_key is None
