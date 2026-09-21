from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolComponentReference,
    AlarmToolReference,
    AlarmToolReferenceCatalog,
    AlarmToolSubcomponentReference,
)
from ada_command_center.web.alarms.configuration.web.authoring import (
    add_component_key,
    add_rule,
    add_subcomponent,
    add_visual_target,
    component_suggestions,
    empty_authoring_document,
    set_component_key,
    set_message_field,
    set_subcomponent_field,
    set_visual_target_field,
    subcomponent_suggestions,
    tool_reference_catalog_to_document,
)
from atlanticus.web.source.models import SourceReleaseId


def test_new_rule_keeps_required_business_fields_explicitly_unset() -> None:
    document = add_rule(empty_authoring_document())

    rule = document['rules'][0]
    assert rule['identity'] == {'family_key': '', 'alarm_key': ''}
    assert rule['kind'] is None
    assert rule['criticality'] is None
    assert rule['is_active'] is None
    assert rule['escalation'] == {'origin_tool_key': '', 'steps': []}
    assert rule['visual_targets'] == []


def test_visual_target_tool_change_clears_previous_tool_namespace() -> None:
    document = add_rule(empty_authoring_document())
    document = add_visual_target(document, 0)
    document = set_visual_target_field(document, 0, 0, 'tool_key', 'tool-a')
    document = add_component_key(document, 0, 0)
    document = set_component_key(document, 0, 0, 0, 'component-a')
    document = add_subcomponent(document, 0, 0)
    document = set_subcomponent_field(document, 0, 0, 0, 'owner_component_key', 'component-a')
    document = set_subcomponent_field(document, 0, 0, 0, 'subcomponent_key', 'sub-a')

    updated = set_visual_target_field(document, 0, 0, 'tool_key', 'tool-b')

    target = updated['rules'][0]['visual_targets'][0]
    assert target['tool_key'] == 'tool-b'
    assert target['component_keys'] == []
    assert target['subcomponents'] == []


def test_same_manual_tool_key_preserves_existing_addresses() -> None:
    document = add_rule(empty_authoring_document())
    document = add_visual_target(document, 0)
    document = set_visual_target_field(document, 0, 0, 'tool_key', 'manual-tool')
    document = add_component_key(document, 0, 0)
    document = set_component_key(document, 0, 0, 0, 'manual-component')

    updated = set_visual_target_field(document, 0, 0, 'tool_key', 'manual-tool')

    target = updated['rules'][0]['visual_targets'][0]
    assert target['component_keys'] == ['manual-component']


def test_tool_reference_document_preserves_linked_subcomponent_owner() -> None:
    catalog = AlarmToolReferenceCatalog(
        catalog_revision='catalog-rev',
        tools=(
            AlarmToolReference(
                tool_key='tool-a',
                display_name='Tool A',
                kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                source_release_id=SourceReleaseId('release-a'),
                components=(
                    AlarmToolComponentReference(
                        component_key='component-visible',
                        display_name='Visible component',
                        subcomponents=(
                            AlarmToolSubcomponentReference(
                                owner_component_key='component-owner',
                                subcomponent_key='sub-a',
                                display_name='Sub A',
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    document = tool_reference_catalog_to_document(catalog)

    assert document is not None
    assert component_suggestions(document, 'tool-a') == (
        {
            'value': 'component-visible',
            'label': 'Visible component (component-visible)',
        },
    )
    assert subcomponent_suggestions(document, 'tool-a', ['component-visible']) == (
        {
            'owner_component_key': 'component-owner',
            'subcomponent_key': 'sub-a',
            'display_name': 'Sub A',
        },
    )


def test_global_message_scope_clears_family_key() -> None:
    document = {
        'rules': [],
        'messages': [
            {
                'message_key': 'message-a',
                'scope': 'FAMILY',
                'family_key': 'family-a',
                'display_text': 'Message',
                'is_active': True,
                'deactivation_override': None,
            }
        ],
    }

    updated = set_message_field(document, 0, 'scope', 'GLOBAL')

    assert updated['messages'][0]['scope'] == 'GLOBAL'
    assert updated['messages'][0]['family_key'] is None
