from __future__ import annotations

from collections.abc import Mapping


class IntegratedAlarmSelectionError(ValueError):
    pass


def is_integrated_tool(tool: Mapping[str, object]) -> bool:
    alarms = tool.get('alarms')
    if not isinstance(alarms, Mapping):
        raise IntegratedAlarmSelectionError('Modeler tool alarms must be a mapping')
    kinds: set[str] = set()
    for alarm in alarms.values():
        if not isinstance(alarm, Mapping):
            raise IntegratedAlarmSelectionError('Modeler alarm must be a mapping')
        target = alarm.get('visual_target')
        if not isinstance(target, Mapping):
            raise IntegratedAlarmSelectionError('Modeler visual target is invalid')
        kind = target.get('tool_kind')
        if not isinstance(kind, str):
            raise IntegratedAlarmSelectionError('Modeler target tool kind is missing')
        kinds.add(kind)
    if len(kinds) > 1:
        raise IntegratedAlarmSelectionError('Modeler tool has inconsistent target kinds')
    return 'integrated_operations' in kinds


def project_integrated_slots(
    operator_pool: list[str],
    alarms: Mapping[str, object],
    *,
    max_visible_slots: int,
) -> list[dict[str, object]]:
    if max_visible_slots != 6:
        raise IntegratedAlarmSelectionError('Integrated Operations requires six visible slots')
    selected: dict[str, list[tuple[str, str]]] = {'mine': [], 'plant': []}
    seen_components: set[str] = set()
    for occurrence_id in operator_pool:
        record = alarms.get(occurrence_id)
        if not isinstance(record, Mapping):
            raise IntegratedAlarmSelectionError('Integrated Operations pool contains unknown alarm')
        target = record.get('visual_target')
        if not isinstance(target, Mapping) or target.get('tool_kind') != 'integrated_operations':
            raise IntegratedAlarmSelectionError('Integrated Operations visual target is invalid')
        scope = target.get('display_scope')
        component = target.get('display_component_key')
        affected = target.get('component_keys')
        if not isinstance(scope, str) or scope not in selected:
            raise IntegratedAlarmSelectionError('Integrated Operations display scope is invalid')
        if (
            not isinstance(component, str)
            or not component
            or not isinstance(affected, list)
            or component not in affected
        ):
            raise IntegratedAlarmSelectionError(
                'Integrated Operations display component is invalid'
            )
        if component in seen_components:
            continue
        seen_components.add(component)
        if len(selected[scope]) < 3:
            selected[scope].append((component, occurrence_id))
    return [
        {'slot': start + index, 'occurrence_id': occurrence_id}
        for scope, start in (('mine', 1), ('plant', 4))
        for index, (_, occurrence_id) in enumerate(selected[scope])
    ]


def validate_integrated_slots(tool: Mapping[str, object]) -> None:
    if not is_integrated_tool(tool):
        return
    alarms = tool['alarms']
    slots = tool['meta']['max_visible_slots']
    if slots != 6:
        raise IntegratedAlarmSelectionError('Integrated Operations requires six visible slots')
    occupied_components: set[str] = set()
    for item in tool['operator_view']:
        if not isinstance(item, Mapping) or set(item) != {'slot', 'occurrence_id'}:
            raise IntegratedAlarmSelectionError('Integrated Operations operator slot is invalid')
        record = alarms.get(item['occurrence_id'])
        if not isinstance(record, Mapping):
            raise IntegratedAlarmSelectionError(
                'Integrated Operations operator occurrence is invalid'
            )
        target = record.get('visual_target')
        if not isinstance(target, Mapping):
            raise IntegratedAlarmSelectionError('Integrated Operations visual target is invalid')
        scope = target.get('display_scope')
        component = target.get('display_component_key')
        slot = item['slot']
        if scope == 'mine':
            valid_slot = type(slot) is int and 1 <= slot <= 3
        elif scope == 'plant':
            valid_slot = type(slot) is int and 4 <= slot <= 6
        else:
            valid_slot = False
        if not valid_slot or not isinstance(component, str) or component in occupied_components:
            raise IntegratedAlarmSelectionError(
                'Integrated Operations placement conflicts with a component'
            )
        occupied_components.add(component)
    expected = project_integrated_slots(
        tool['operator_pool'],
        alarms,
        max_visible_slots=6,
    )
    if tool['operator_view'] != expected:
        raise IntegratedAlarmSelectionError(
            'Integrated Operations view must show first eligible occurrences'
        )
