from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    AlarmStatus,
    EvidenceContractRef,
    PlannedAlarm,
)
from ada_command_center.alarms.materialization.codec import (
    delivery_to_document,
    runtime_to_document,
)
from ada_command_center.alarms.materialization.delivery import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
)
from ada_command_center.alarms.materialization.local_reader import (
    LocalAlarmMaterializationReader,
    materialization_result_id,
    materialization_root,
)
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    VisibilityMode,
)
from ada_command_center.processes.alarms_delivery.job import build_delivery_input_job
from ada_command_center.processes.alarms_runtime import (
    AlarmConfigurationAdoptionExecutor,
    AlarmEvaluatorRegistry,
    AlarmIterationLoader,
    AlarmOperationalCycle,
    build_alarm_configuration_revision,
    build_alarm_runtime_composition,
    build_alarm_source_adapter,
)
from ada_command_center.processes.alarms_runtime.catalog.examples.threshold import (
    build_threshold_contract,
)
from ada_command_center.processes.alarms_runtime.inputs import AlarmOperationalInputs
from ada_command_center.processes.alarms_runtime.publication import (
    AlarmCommittedFactsExporter,
    AlarmCurrentStatePublisher,
)
from atlanticus.kernel import Environment
from atlanticus.operational_data.sources import DataSourceApplications, PiSourceProvider
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration
from atlanticus.state import AtomicJsonStore

_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
_SOURCE = 'alarm-configuration'


class _DatasetRuntime:
    def __init__(self):
        self.temperature = 82.0

    def scan_dataframe(self, *, definition, targets, projection_schema, filters):
        values = pd.DataFrame(
            {
                'timestamp_utc': [
                    pd.Timestamp(_AT - timedelta(hours=3)),
                    pd.Timestamp(_AT - timedelta(minutes=45)),
                    pd.Timestamp(_AT - timedelta(minutes=5)),
                ],
                'temperature': [90.0, 75.0, self.temperature],
            }
        )
        return SimpleNamespace(dataframe=values.loc[:, list(projection_schema.names)])


class _CommitTime:
    def committed_at(self, *, cycle_at):
        return cycle_at


def _config(volume: Path) -> RuntimeConfiguration:
    return RuntimeConfiguration(
        environment=Environment.from_value('local'),
        application='ada-command-center',
        volume_path=volume,
    )


def _context(configuration: RuntimeConfiguration, *, service: str, run_id: str):
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name=f'ada_command_center.processes.alarms_{service}',
            service_name=f'alarms-{service}',
        ),
        configuration=configuration,
        run_id=run_id,
        correlation_id=run_id,
        wall_clock=lambda: _AT,
    )

    @contextmanager
    def fence():
        yield

    context._bind_lease_authority(generation=1, checker=lambda: None, fence=fence)
    return context


def _write(path: Path, value: dict) -> tuple[str, int]:
    content = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha256(content).hexdigest(), len(content)


def _ready(volume: Path, plan: PlannedAlarm):
    key = AlarmResolutionKey('R10', 'C5')
    runtime = RuntimeAlarmConfiguration(
        resolution_key=key,
        defined_alarm_identities=(plan.identity,),
        planned_alarms=(plan,),
        parameters_by_alarm={},
    )
    delivery = DeliveryAlarmConfiguration(
        resolution_key=key,
        alarms=(
            ResolvedDeliveryAlarm(
                identity=plan.identity,
                is_active=True,
                visibility_mode=VisibilityMode.VISIBLE,
                display_name='Temperature',
                title='Temperature high',
                cause_template='Temperature {observed_value}',
                kind=AlarmKind.RISK,
                criticality=Criticality.C3,
                business_category=BusinessCategory.SAFETY_HEALTH,
                operational_areas=(OperationalArea.MINE,),
                color=AlarmColor.RED,
                default_deactivation_policy=ResolvedDeactivationPolicy(
                    enabled=False, max_duration_hours=None, approval_required=False
                ),
            ),
        ),
    )
    root = materialization_root(volume)
    result_id = materialization_result_id(
        source_key=_SOURCE, projection_digest='a' * 64, qualification_digest='b' * 64
    )
    version = root / 'versions' / result_id
    inventory = {}
    for label, payload in (
        ('runtime', runtime_to_document(runtime)),
        ('delivery', delivery_to_document(delivery)),
    ):
        digest, size = _write(version / f'{label}.json', payload)
        inventory[label] = {
            'path': f'{label}.json',
            'sha256': digest,
            'size_bytes': size,
        }
    manifest = {
        'document_type': 'ada_command_center_alarm_materialization_result',
        'schema_version': 1,
        'source_key': _SOURCE,
        'result_id': result_id,
        'status': 'READY',
        'resolution_key': {
            'alarm_configuration_revision': 'R10',
            'confirmed_tool_catalog_revision': 'C5',
        },
        'provenance': {
            'source_release_id': 'R10',
            'source_published_at_utc': '2026-09-28T13:00:00Z',
            'confirmed_tool_catalog_revision': 'C5',
            'projection_digest': 'a' * 64,
            'qualification_digest': 'b' * 64,
            'qualification_producer': 'integration-test',
            'qualification_evidence_ref': 'integration-1',
            'qualified_at_utc': '2026-09-28T13:30:00Z',
        },
        'findings': [],
        'artifacts': inventory,
    }
    manifest_sha256, _ = _write(version / 'manifest.json', manifest)
    _write(
        root / 'ready.json',
        {
            'document_type': 'ada_command_center_alarm_materialization_ready',
            'schema_version': 1,
            'source_key': _SOURCE,
            'result_id': result_id,
            'resolution_key': manifest['resolution_key'],
            'manifest_sha256': manifest_sha256,
        },
    )
    return LocalAlarmMaterializationReader(root=root).read_exact_ready(
        source_key=_SOURCE, result_id=result_id, manifest_sha256=manifest_sha256
    )


def _engine_cycle(session, composition):
    return AlarmOperationalCycle(
        session=session,
        composition=composition,
        occurrence_id_factory=lambda identity, at: f'occ-{identity.alarm_key}',
        episode_id_factory=lambda group, at: f'episode-{group}',
        commit_time_provider=_CommitTime(),
        runtime_artifact_version='1.0.0',
        technical_evidence_contract=EvidenceContractRef(
            contract_key='integration.technical', contract_version='v1'
        ),
    )


def _engine_output_root(volume: Path) -> Path:
    return volume / 'ada-command-center' / 'alarms' / 'runtime' / 'output'


def _inbox(volume: Path) -> AtomicJsonStore:
    return AtomicJsonStore(
        root_path=volume / 'ada-command-center' / 'alarms' / 'delivery' / 'input',
        max_document_bytes=None,
    )


def _delivery(configuration: RuntimeConfiguration, *, run_id: str):
    job = build_delivery_input_job(runtime_configuration=configuration, source_key=_SOURCE)
    context = _context(configuration, service='delivery', run_id=run_id)
    job.recover(context)
    context._begin_iteration(1)
    return job, context


def test_real_engine_current_and_durable_facts_survive_independent_delivery_restart(tmp_path):
    plan = PlannedAlarm(
        identity=AlarmIdentity('mina', 'temperature'),
        kind=AlarmKind.RISK,
        criticality=Criticality.C3,
        priority_group='mine-temperature',
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        routing=AlarmRouting(origin_tool_key='mine'),
    )
    ready = _ready(tmp_path, plan)
    registry = AlarmEvaluatorRegistry(contracts=(build_threshold_contract(),))
    revision = build_alarm_configuration_revision(candidate=ready, evaluator_registry=registry)
    session = revision.session
    configuration = _config(tmp_path)
    composition = build_alarm_runtime_composition(runtime_configuration=configuration)
    engine_context = _context(configuration, service='runtime', run_id='engine-1')
    composition.recover(engine_context)
    adoption = AlarmConfigurationAdoptionExecutor(
        composition=composition,
        commit_time_provider=_CommitTime(),
        runtime_artifact_version='1.0.0',
    )
    adoption.bootstrap(
        engine_context,
        revision,
        effective_at=_AT - timedelta(minutes=1),
        adoption_id='adoption-1',
    )
    persistence = composition.durability.persistence
    pin = persistence.read_effective_head().target_artifact_ref
    exporter = AlarmCommittedFactsExporter(root=_engine_output_root(tmp_path), source_key=_SOURCE)
    current = AlarmCurrentStatePublisher(root=_engine_output_root(tmp_path), source_key=_SOURCE)
    assert exporter.initialize_if_needed(context=engine_context, persistence=persistence, pin=pin)

    dataset = _DatasetRuntime()
    adapter = build_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source=PiSourceProvider.NOTPII,
        applications=DataSourceApplications(pi='operational-pi'),
        runtime_factory=lambda path: dataset,
    )
    engine_context._begin_iteration(1)
    iteration = AlarmIterationLoader(session=session, source_loader=adapter).load(as_of=_AT)
    started = _engine_cycle(session, composition).execute(
        engine_context, iteration, operational_inputs=AlarmOperationalInputs()
    )
    assert started.evaluation_for(plan.identity).status is AlarmStatus.ACTIVE
    assert current.publish(
        context=engine_context, result=started, pin=pin, inputs=AlarmOperationalInputs()
    )
    assert (
        exporter.publish_unexported(context=engine_context, persistence=persistence, pin=pin) == 1
    )

    delivery, delivery_context = _delivery(configuration, run_id='delivery-1')
    received = delivery.iteration(delivery_context)
    assert received.current_status == 'CURRENT_STAGED'
    assert received.staged_facts == 1
    inbox = _inbox(tmp_path)
    first = inbox.read('current/latest.json')
    assert len(first['state']['alarms']) == 1
    evidence = first['state']['alarms'][0]['evaluation']['evidence']['payload']
    assert evidence['observed_value'] == 82.0
    assert len(tuple((delivery.receiver.inbox_root / 'facts').glob('*.json'))) == 1

    dataset.temperature = 70.0
    restarted_composition = build_alarm_runtime_composition(runtime_configuration=configuration)
    restarted_engine = _context(configuration, service='runtime', run_id='engine-2')
    restarted_composition.recover(restarted_engine)
    restarted_exporter = AlarmCommittedFactsExporter(
        root=_engine_output_root(tmp_path), source_key=_SOURCE
    )
    assert not restarted_exporter.initialize_if_needed(
        context=restarted_engine, persistence=restarted_composition.durability.persistence, pin=pin
    )
    restarted_engine._begin_iteration(1)
    next_at = _AT + timedelta(minutes=1)
    closed = _engine_cycle(session, restarted_composition).execute(
        restarted_engine,
        AlarmIterationLoader(session=session, source_loader=adapter).load(as_of=next_at),
        operational_inputs=AlarmOperationalInputs(),
    )
    assert closed.evaluation_for(plan.identity).status is AlarmStatus.INACTIVE
    assert current.publish(
        context=restarted_engine, result=closed, pin=pin, inputs=AlarmOperationalInputs()
    )
    assert (
        restarted_exporter.publish_unexported(
            context=restarted_engine,
            persistence=restarted_composition.durability.persistence,
            pin=pin,
        )
        == 1
    )

    delivery_after_restart, context_after_restart = _delivery(configuration, run_id='delivery-2')
    second = delivery_after_restart.iteration(context_after_restart)
    assert second.current_status == 'CURRENT_STAGED'
    assert second.staged_facts == 1
    assert inbox.read('current/latest.json')['state']['alarms'] == []
    received_batches = [
        inbox.read(f'facts/{path.name}')
        for path in sorted((delivery_after_restart.receiver.inbox_root / 'facts').glob('*.json'))
    ]
    assert len(received_batches) == 2
    events = [
        event['event_key']
        for batch in received_batches
        for event in batch['records'].get('journey_events', [])
    ]
    assert 'occurrence_started' in events
    assert 'occurrence_closed' in events
    for batch in received_batches:
        assert batch['commit_record_hash'] == batch['batch_id'].replace('facts-', 'sha256:', 1)
    context_after_restart._begin_iteration(2)
    repeat = delivery_after_restart.iteration(context_after_restart)
    assert repeat.current_status == 'CURRENT_UNCHANGED'
    assert repeat.staged_facts == 0
    assert len(list((delivery_after_restart.receiver.inbox_root / 'facts').glob('*.json'))) == 2
    batches = sorted(
        received_batches,
        key=lambda batch: (
            batch['journal_position']['segment_id'],
            batch['journal_position']['byte_offset'],
        ),
    )
    assert batches[0]['schema_version'] == 2
    assert batches[0]['previous_batch'] is None
    assert batches[1]['schema_version'] == 2
    assert batches[1]['previous_batch'] == {
        'batch_id': batches[0]['batch_id'],
        'sha256': batches[0]['sha256'],
    }
