from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from ada_command_center.alarms.core import (
    AlarmRouting,
    AlarmStatus,
    EvidenceContractRef,
    PlannedAlarm,
)
from ada_command_center.domain.alarms import AlarmIdentity, AlarmKind, Criticality
from ada_command_center.processes.alarms_runtime import (
    AlarmIterationLoader,
    AlarmOperationalCycle,
    build_alarm_execution_session,
    build_alarm_runtime_composition,
    build_alarm_source_adapter,
)
from ada_command_center.processes.alarms_runtime.catalog import build_alarm_evaluator_registry
from atlanticus.kernel import Environment
from atlanticus.operational_data.core import DataPartition, DataSource
from atlanticus.operational_data.sources import DataSourceApplications, PiSourceProvider
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration

_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


class _ControlledDatasetRuntime:
    def __init__(self):
        self.calls = []
        self.data = pd.DataFrame(
            {
                'timestamp_utc': [
                    pd.Timestamp(_AT - timedelta(hours=3)),
                    pd.Timestamp(_AT - timedelta(minutes=45)),
                    pd.Timestamp(_AT - timedelta(minutes=5)),
                ],
                'temperature': [90.0, 75.0, 82.0],
            }
        )

    def scan_dataframe(self, *, definition, targets, projection_schema, filters):
        self.calls.append((definition.key.identifier, targets[0], projection_schema.names))
        assert targets[0].materialization == 'daily'
        return SimpleNamespace(dataframe=self.data.loc[:, list(projection_schema.names)])


class _CommitTime:
    def committed_at(self, *, cycle_at: datetime) -> datetime:
        return cycle_at


def _alarm(key: str, order: int) -> PlannedAlarm:
    return PlannedAlarm(
        identity=AlarmIdentity('mina', key),
        kind=AlarmKind.RISK,
        criticality=Criticality.C3,
        priority_group='mina-threshold',
        priority_order=order,
        evaluator_key='threshold',
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        routing=AlarmRouting(origin_tool_key='mine'),
    )


def test_example_shared_read_optional_parameters_and_durable_evidence(tmp_path: Path):
    first, second = _alarm('first', 1), _alarm('second', 2)
    session = build_alarm_execution_session(
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        planned_alarms=(first, second),
        evaluator_registry=build_alarm_evaluator_registry(),
        parameters_by_alarm={second.identity: {'limit': 90.0}},
    )
    assert session.entry_for(first.identity).parameters == {}
    assert len(session.data_plan.views) == 1
    runtime = _ControlledDatasetRuntime()
    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=DataSourceApplications(pi='operational-pi'),
        runtime_factory=lambda path: runtime,
    )
    iteration = AlarmIterationLoader(session=session, source_loader=adapter).load(as_of=_AT)
    assert len(runtime.calls) == 1
    assert set(runtime.calls[0][2]) == {'timestamp_utc', 'temperature'}
    assert iteration.data_for(first.identity).get(
        DataSource.PI_INTERPOLATED, DataPartition.DAILY
    ).dataframe['temperature'].tolist() == [90.0, 75.0, 82.0]
    assert iteration.data_for(second.identity).get(
        DataSource.PI_INTERPOLATED, DataPartition.DAILY
    ).dataframe['temperature'].tolist() == [90.0, 75.0, 82.0]

    configuration = RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=tmp_path,
    )
    composition = build_alarm_runtime_composition(runtime_configuration=configuration)
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name='ada_command_center.processes.alarms_runtime',
            service_name='alarms-runtime',
        ),
        configuration=configuration,
        run_id='example-cycle',
        correlation_id='example-cycle',
        wall_clock=lambda: _AT,
    )

    @contextmanager
    def fence():
        yield

    context._bind_lease_authority(generation=1, checker=lambda: None, fence=fence)
    composition.recover(context)
    context._begin_iteration(1)
    cycle = AlarmOperationalCycle(
        session=session,
        composition=composition,
        occurrence_id_factory=lambda identity, at: f'occ-{identity.alarm_key}',
        episode_id_factory=lambda group, at: f'episode-{group}',
        commit_time_provider=_CommitTime(),
        runtime_artifact_version='1.0.0',
        technical_evidence_contract=EvidenceContractRef(
            contract_key='example.technical', contract_version='v1'
        ),
    )
    result = cycle.execute(context, iteration)
    active = result.evaluation_for(first.identity)
    inactive = result.evaluation_for(second.identity)
    assert active.status is AlarmStatus.ACTIVE
    assert inactive.status is AlarmStatus.INACTIVE
    assert active.evidence_snapshot.payload['limit'] == 80.0
    assert inactive.evidence_snapshot.payload['limit'] == 90.0
    assert active.evidence_snapshot.payload['observed_value'] == 82.0
    assert inactive.evidence_snapshot.payload['observed_value'] == 82.0
    assert result.commit_result is not None
    assert result.commit_result.record_count == 1
    assert len(composition.durability.persistence.read_durable_records()) == 1
    snapshot = composition.durability.persistence.read_snapshot('mina-threshold')
    assert snapshot is not None
    assert len(result.materializations) == 1
    initial_evidence = result.materializations[0].records.evidence_records
    assert len(initial_evidence) == 1
    assert initial_evidence[0].alarm_identity == first.identity
    assert initial_evidence[0].evaluation.evidence_snapshot.payload['limit'] == 80.0
