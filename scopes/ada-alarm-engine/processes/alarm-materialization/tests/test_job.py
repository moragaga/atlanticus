from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest



from ada.alarms.persistence import LocalAlarmMaterializationStore
from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmColor,
    AlarmConfiguration,
    AlarmConfigurationProjection,
    AlarmConfigurationSnapshot,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada.contracts.tools import ToolDependencyEntry, ToolDependencyManifest
from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.processes.alarm_materialization import (
    AlarmMaterializationCandidate,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
    AlarmMaterializationSupersededError,
)


class FakeContext:
    def __init__(self) -> None:
        self.facts: dict[str, object] = {}
        self.work_count = 0
        self.next_delay: float | None = None
        self.fenced_count = 0

    def raise_if_cancelled(self) -> None:
        return None

    def assert_lease_current(self) -> None:
        return None

    @contextmanager
    def fenced_mutation(self):
        self.fenced_count += 1
        yield

    def mark_iteration_work(self) -> None:
        self.work_count += 1

    def set_iteration_fact(self, key: str, value: object) -> None:
        self.facts[key] = value

    def set_next_iteration_delay(self, seconds: float) -> None:
        self.next_delay = seconds


class StaticReader:
    def __init__(self, candidate: AlarmMaterializationCandidate) -> None:
        self.candidate = candidate
        self.calls = 0

    def read_active(self) -> AlarmMaterializationCandidate:
        self.calls += 1
        return self.candidate


class ChangingReader:
    def __init__(
        self,
        first: AlarmMaterializationCandidate,
        second: AlarmMaterializationCandidate,
    ) -> None:
        self.values = (first, second)
        self.calls = 0

    def read_active(self) -> AlarmMaterializationCandidate:
        value = self.values[min(self.calls, 1)]
        self.calls += 1
        return value


class PendingReader:
    def read_active(self) -> AlarmMaterializationCandidate:
        raise AlarmMaterializationConfigurationPending(
            'Alarm Configuration projection is not available yet'
        )




def test_job_publishes_ready_then_becomes_unchanged(tmp_path: Path) -> None:
    candidate = _candidate()
    reader = StaticReader(candidate)
    store = LocalAlarmMaterializationStore(root=tmp_path / 'materialization')
    job = AlarmMaterializationJob(
        reader=reader,
        store=store,
    )

    first_context = FakeContext()
    first = job.run_iteration(first_context)
    second_context = FakeContext()
    second = job.run_iteration(second_context)

    assert first.outcome is AlarmMaterializationOutcome.READY
    assert first.result_id is not None
    assert first_context.work_count == 1
    assert store.read_published_ready(source_key=ALARM_CONFIGURATION_SOURCE_KEY) is not None
    assert second.outcome is AlarmMaterializationOutcome.UNCHANGED
    assert second.result_id == first.result_id
    assert second_context.work_count == 0


def test_job_persists_blocked_without_replacing_ready(tmp_path: Path) -> None:
    ready_candidate = _candidate()
    store = LocalAlarmMaterializationStore(root=tmp_path / 'materialization')
    ready_job = AlarmMaterializationJob(
        reader=StaticReader(ready_candidate),
        store=store,
    )
    ready = ready_job.run_iteration(FakeContext())
    current_before = store.read_published_ready(source_key=ALARM_CONFIGURATION_SOURCE_KEY)

    blocked_candidate = _candidate(blocked=True, release='alarm-r8', missing_tool=True)
    blocked_job = AlarmMaterializationJob(
        reader=StaticReader(blocked_candidate),
        store=store,
    )
    blocked = blocked_job.run_iteration(FakeContext())
    current_after = store.read_published_ready(source_key=ALARM_CONFIGURATION_SOURCE_KEY)

    assert ready.outcome is AlarmMaterializationOutcome.READY
    assert blocked.outcome is AlarmMaterializationOutcome.BLOCKED
    assert blocked.result_id is not None
    assert (
        store.read_result(
            source_key=ALARM_CONFIGURATION_SOURCE_KEY,
            result_id=blocked.result_id,
        ).manifest.status.value
        == 'BLOCKED'
    )
    assert current_after is not None
    assert current_before is not None
    assert current_after.result_id == current_before.result_id


def test_job_treats_missing_projection_as_pending_without_mutation(tmp_path: Path) -> None:
    job = AlarmMaterializationJob(
        reader=PendingReader(),
        store=LocalAlarmMaterializationStore(root=tmp_path / 'materialization'),
    )
    context = FakeContext()

    result = job.run_iteration(context)

    assert result.outcome is AlarmMaterializationOutcome.PENDING
    assert result.result_id is None
    assert context.next_delay == 30.0
    assert context.fenced_count == 0
    assert context.work_count == 0


def test_job_rejects_projection_changed_before_publication(tmp_path: Path) -> None:
    first = _candidate()
    second = _candidate(projected_minute=2)
    store = LocalAlarmMaterializationStore(root=tmp_path / 'materialization')
    job = AlarmMaterializationJob(
        reader=ChangingReader(first, second),
        store=store,
    )

    with pytest.raises(AlarmMaterializationSupersededError):
        job.run_iteration(FakeContext())

    assert store.read_published_ready(source_key=ALARM_CONFIGURATION_SOURCE_KEY) is None




def _candidate(
    *,
    blocked: bool = False,
    release: str = 'alarm-r7',
    projected_minute: int = 1,
    missing_tool: bool = False,
) -> AlarmMaterializationCandidate:
    configuration = AlarmConfiguration(
        rules=(_rule(),) if blocked else (),
        messages=(),
    )
    tools = (_tool_entry(),) if blocked and not missing_tool else ()
    projection = AlarmConfigurationProjection(
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        source_release_id=release,
        source_published_at_utc=datetime(2026, 10, 7, 12, tzinfo=UTC),
        projected_at_utc=datetime(2026, 10, 7, 12, projected_minute, tzinfo=UTC),
        snapshot=AlarmConfigurationSnapshot(
            configuration=configuration,
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r9',
                tools=tools,
            ),
        ),
    )
    return AlarmMaterializationCandidate.capture(projection)




def _rule() -> AlarmDefinition:
    return AlarmDefinition(
        identity=AlarmIdentity(family_key='mill', alarm_key='risk'),
        rule_name='risk-rule',
        display_name='Risk',
        title='Risk alarm',
        cause_template='Value exceeds threshold',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        evaluator_key='threshold',
        parameters={'limit': 10.0},
        priority_group='mill-feed',
        priority_order=1,
        message_keys=(),
        reappearance=ReappearanceDefinition(),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=4,
            approval_required=True,
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='tool_a'),
        visual_targets=(),
    )


def _tool_entry() -> ToolDependencyEntry:
    structure = ToolStructure(
        tool_key='tool_a',
        kind=ToolConfigurationKind.PROCESS,
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
                subcomponents=(ToolSubcomponent(key='pressure', display_name='Pressure'),),
            ),
        ),
        operational_scope=ToolScope.PLANT,
        center_component_key='main',
    )
    return ToolDependencyEntry(
        tool_key='tool_a',
        display_name='Tool A',
        source_release_id='tool-a-r1',
        kind=ToolConfigurationKind.PROCESS,
        structure=structure,
    )
