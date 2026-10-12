from __future__ import annotations

from ada.alarms.materialization import (
    AlarmResolutionStatus,
    modeler_from_document,
    modeler_to_document,
    resolve_alarm_configuration,
)
from ada.contracts.alarms import (
    AlarmConfiguration,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
)
from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent

from .test_resolver import CatalogEntry, ConfirmedToolCatalog, process_entry, rule


def integrated_entry() -> CatalogEntry:
    return CatalogEntry(
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=ToolStructure(
            tool_key='tool_a',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='general_mine',
                    display_name='General Mine',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='mine_01', display_name='Mine 01'),),
                ),
                ToolComponent(
                    key='haulage',
                    display_name='Haulage',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='haul_01', display_name='Haul 01'),),
                ),
                ToolComponent(
                    key='plant',
                    display_name='Plant',
                    scope=ToolScope.PLANT,
                    subcomponents=(ToolSubcomponent(key='plant_01', display_name='Plant 01'),),
                ),
            ),
        ),
    )


def resolve(target: AlarmVisualTarget, *, integrated: bool = True):
    configuration = AlarmConfiguration(
        rules=(rule(alarm_key='risk', visual_targets=(target,)),),
        messages=(),
    )
    catalog = ConfirmedToolCatalog(
        revision='TOOLS-DISPLAY-1',
        entries={'tool_a': integrated_entry() if integrated else process_entry('tool_a')},
    )
    return resolve_alarm_configuration(configuration, 'ALARMS-DISPLAY-1', catalog)


def test_integrated_location_materializes_and_roundtrips() -> None:
    target = AlarmVisualTarget(
        tool_key='tool_a',
        component_keys=('general_mine', 'haulage'),
        display_component_key='general_mine',
        subcomponents=(AlarmVisualSubcomponentTarget('haulage', 'haul_01'),),
    )
    result = resolve(target)
    assert result.status is AlarmResolutionStatus.READY
    materialized = result.modeler_configuration
    assert materialized is not None
    actual = materialized.alarms[0].visual_targets[0]
    assert actual.display_component_key == 'general_mine'
    assert actual.display_scope is ToolScope.MINE
    assert actual.component_keys == ('general_mine', 'haulage')
    assert actual.subcomponents[0].owner_component_key == 'haulage'
    assert modeler_from_document(modeler_to_document(materialized)) == materialized


def test_integrated_requires_display_component() -> None:
    target = AlarmVisualTarget(tool_key='tool_a', component_keys=('general_mine',))
    result = resolve(target)
    assert result.status is AlarmResolutionStatus.BLOCKED
    assert any(finding.code == 'display_component_required' for finding in result.findings)
    assert result.modeler_configuration is None


def test_process_rejects_display_component() -> None:
    target = AlarmVisualTarget(
        tool_key='tool_a',
        component_keys=('main',),
        display_component_key='main',
    )
    result = resolve(target, integrated=False)
    assert result.status is AlarmResolutionStatus.BLOCKED
    assert any(finding.code == 'display_component_unexpected' for finding in result.findings)


def test_process_without_display_component_still_resolves() -> None:
    target = AlarmVisualTarget(tool_key='tool_a', component_keys=('main',))
    result = resolve(target, integrated=False)
    assert result.status is AlarmResolutionStatus.READY
    actual = result.modeler_configuration.alarms[0].visual_targets[0]
    assert actual.display_component_key == 'main'
    assert (
        modeler_from_document(modeler_to_document(result.modeler_configuration))
        == result.modeler_configuration
    )


def test_process_center_is_not_necessarily_an_affected_component() -> None:
    target = AlarmVisualTarget(tool_key='tool_a', component_keys=())
    result = resolve(target, integrated=False)
    assert result.status is AlarmResolutionStatus.READY
    resolved = result.modeler_configuration.alarms[0].visual_targets[0]
    assert resolved.component_keys == ()
    assert resolved.display_component_key == 'main'
    assert resolved.display_scope is None
