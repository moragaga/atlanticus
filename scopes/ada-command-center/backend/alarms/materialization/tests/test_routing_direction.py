import pytest

from ada.web.tools.enums import ToolConfigurationKind as Kind
from ada_command_center.alarms.materialization import (
    AlarmResolutionStatus,
    resolve_alarm_configuration,
)
from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    Criticality,
)

from .test_resolver import (
    ConfirmedToolCatalog,
    catalog_entry,
    evaluator_qualification,
    green_qualification,
    rule,
)


@pytest.mark.parametrize(
    ('origin', 'destinations', 'expected'),
    [
        (Kind.PROCESS, (), AlarmResolutionStatus.READY),
        (Kind.INTEGRATED_OPERATIONS, (), AlarmResolutionStatus.READY),
        (Kind.STRATEGIC, (), AlarmResolutionStatus.READY),
        (Kind.PROCESS, (Kind.INTEGRATED_OPERATIONS,), AlarmResolutionStatus.READY),
        (Kind.PROCESS, (Kind.INTEGRATED_OPERATIONS, Kind.STRATEGIC), AlarmResolutionStatus.READY),
        (Kind.INTEGRATED_OPERATIONS, (Kind.STRATEGIC,), AlarmResolutionStatus.READY),
        (Kind.PROCESS, (Kind.PROCESS,), AlarmResolutionStatus.BLOCKED),
        (Kind.PROCESS, (Kind.STRATEGIC,), AlarmResolutionStatus.BLOCKED),
        (Kind.INTEGRATED_OPERATIONS, (Kind.PROCESS,), AlarmResolutionStatus.BLOCKED),
        (Kind.INTEGRATED_OPERATIONS, (Kind.INTEGRATED_OPERATIONS,), AlarmResolutionStatus.BLOCKED),
        (Kind.STRATEGIC, (Kind.PROCESS,), AlarmResolutionStatus.BLOCKED),
        (Kind.STRATEGIC, (Kind.INTEGRATED_OPERATIONS,), AlarmResolutionStatus.BLOCKED),
        (Kind.STRATEGIC, (Kind.STRATEGIC,), AlarmResolutionStatus.BLOCKED),
    ],
)
def test_materialization_enforces_directional_routing(
    origin: Kind,
    destinations: tuple[Kind, ...],
    expected: AlarmResolutionStatus,
) -> None:
    entries = {'origin': catalog_entry('origin', origin)}
    steps = []
    for index, kind in enumerate(destinations, 1):
        tool_key = f'target_{index}'
        entries[tool_key] = catalog_entry(tool_key, kind)
        steps.append(AlarmEscalationStepDefinition(index, tool_key, True, index * 10))
    candidate = AlarmConfiguration(
        rules=(
            rule(
                criticality=Criticality.C2,
                escalation=AlarmEscalationDefinition('origin', tuple(steps)),
            ),
        ),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=candidate,
        alarm_configuration_revision='ALARMS-STRICT',
        confirmed_tool_catalog=ConfirmedToolCatalog('TOOLS-STRICT', entries),
        tool_qualification=green_qualification(*entries),
        evaluator_qualification=evaluator_qualification(),
    )
    assert result.status is expected
    assert tuple(finding.code for finding in result.findings) == (
        () if expected is AlarmResolutionStatus.READY else ('routing_invalid_direction',)
    )
    if expected is AlarmResolutionStatus.READY:
        assert result.runtime_configuration is not None
        assert result.delivery_configuration is not None
        actual = result.runtime_configuration.planned_alarms[0].routing.destinations
        assert tuple(destination.tool_key for destination in actual) == tuple(entries)[1:]
        assert tuple(destination.delay_seconds for destination in actual) == tuple(
            sum(range(1, index + 1)) * 600 for index in range(1, len(steps) + 1)
        )
    else:
        assert result.runtime_configuration is None
        assert result.delivery_configuration is None
        assert result.findings[0].field_path is not None
        assert result.findings[0].field_path.endswith('target_tool_key')


def test_disabled_intermediate_step_cannot_authorize_a_level_skip() -> None:
    kinds = {
        'origin': Kind.PROCESS,
        'intermediate': Kind.INTEGRATED_OPERATIONS,
        'strategic': Kind.STRATEGIC,
    }
    candidate = AlarmConfiguration(
        rules=(
            rule(
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='origin',
                    steps=(
                        AlarmEscalationStepDefinition(1, 'intermediate', False, None),
                        AlarmEscalationStepDefinition(2, 'strategic', True, None),
                    ),
                ),
            ),
        ),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=candidate,
        alarm_configuration_revision='ALARMS-STRICT',
        confirmed_tool_catalog=ConfirmedToolCatalog(
            'TOOLS-STRICT',
            {key: catalog_entry(key, kind) for key, kind in kinds.items()},
        ),
        tool_qualification=green_qualification(*kinds),
        evaluator_qualification=evaluator_qualification(),
    )
    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == ('routing_invalid_direction',)


def test_missing_target_does_not_create_spurious_direction_findings() -> None:
    candidate = AlarmConfiguration(
        rules=(
            rule(
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='origin',
                    steps=(AlarmEscalationStepDefinition(1, 'missing', True),),
                ),
            ),
        ),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=candidate,
        alarm_configuration_revision='ALARMS-STRICT',
        confirmed_tool_catalog=ConfirmedToolCatalog(
            'TOOLS-STRICT',
            {'origin': catalog_entry('origin', Kind.PROCESS)},
        ),
        tool_qualification=green_qualification('origin'),
        evaluator_qualification=evaluator_qualification(),
    )
    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == ('tool_reference_not_found',)


@pytest.mark.parametrize('criticality', [Criticality.C1, Criticality.C2, Criticality.C3])
def test_no_extra_destinations_never_changes_rule_criticality(criticality: Criticality) -> None:
    candidate = AlarmConfiguration(
        rules=(
            rule(
                criticality=criticality,
                escalation=AlarmEscalationDefinition('origin'),
            ),
        ),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=candidate,
        alarm_configuration_revision='ALARMS-STRICT',
        confirmed_tool_catalog=ConfirmedToolCatalog(
            'TOOLS-STRICT',
            {'origin': catalog_entry('origin', Kind.PROCESS)},
        ),
        tool_qualification=green_qualification('origin'),
        evaluator_qualification=evaluator_qualification(),
    )
    assert result.status is AlarmResolutionStatus.READY
    assert result.runtime_configuration is not None
    plan = result.runtime_configuration.planned_alarms[0]
    assert plan.criticality is criticality
    assert plan.routing.destinations == ()
