from dataclasses import replace

import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmVisualTarget,
)
from ada_command_center.domain.tools import ToolDependencyEntry, ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import (
    AlarmConfigurationToolDependencyError,
)
from ada_command_center.web.alarms.configuration.tool_dependencies import (
    WORKSPACE_TOOL_CATALOG_REVISION_KEY,
    pin_workspace_tool_catalog_revision,
    require_workspace_tool_catalog_revision,
    select_alarm_tool_dependencies,
)

from .helpers import message, rule


def _entry(tool_key: str) -> ToolDependencyEntry:
    return ToolDependencyEntry(
        tool_key=tool_key,
        display_name=f'Display {tool_key}',
        source_release_id=f'release-{tool_key}',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=ToolStructure(
            tool_key=tool_key,
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine',
                    display_name='Mine',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='crusher', display_name='Crusher'),),
                ),
            ),
        ),
    )


def _catalog(*tool_keys: str) -> ToolDependencyManifest:
    return ToolDependencyManifest(
        confirmed_tool_catalog_revision='catalog-r7',
        tools=tuple(_entry(tool_key) for tool_key in tool_keys),
    )


def test_select_dependencies_includes_inactive_rules_and_disabled_steps() -> None:
    configured_rule = replace(
        rule(),
        is_active=False,
        escalation=AlarmEscalationDefinition(
            origin_tool_key='tool_a',
            steps=(
                AlarmEscalationStepDefinition(
                    step_order=1,
                    target_tool_key='tool_b',
                    is_enabled=False,
                ),
            ),
        ),
        visual_targets=(AlarmVisualTarget(tool_key='tool_c'),),
    )
    configuration = AlarmConfiguration(
        rules=(configured_rule,),
        messages=(message(),),
    )

    selected = select_alarm_tool_dependencies(
        configuration,
        _catalog('tool_a', 'tool_b', 'tool_c', 'unused_tool'),
    )

    assert selected.revision == 'catalog-r7'
    assert tuple(tool.tool_key for tool in selected.tools) == (
        'tool_a',
        'tool_b',
        'tool_c',
    )
    assert selected.get('tool_c').display_name == 'Display tool_c'


def test_select_dependencies_rejects_unknown_tool_reference() -> None:
    configuration = AlarmConfiguration(rules=(rule(),), messages=(message(),))

    with pytest.raises(
        AlarmConfigurationToolDependencyError,
        match="unknown confirmed Tool 'tool_a'",
    ):
        select_alarm_tool_dependencies(configuration, _catalog('other_tool'))


def test_workspace_tool_revision_sidecar_round_trips_without_mutating_input() -> None:
    payload = {'rules': [], 'messages': []}

    pinned = pin_workspace_tool_catalog_revision(payload, 'catalog-r7')

    assert payload == {'rules': [], 'messages': []}
    assert pinned[WORKSPACE_TOOL_CATALOG_REVISION_KEY] == 'catalog-r7'
    assert require_workspace_tool_catalog_revision(pinned) == 'catalog-r7'
