from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)
from ada_command_center.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
    RuntimeAlarmConfiguration,
)
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    VisibilityMode,
)
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.processes.alarms_materialization.acquisition import AlarmCandidateAcquirer
from ada_command_center.processes.alarms_materialization.codec import (
    delivery_from_document,
    delivery_to_document,
    runtime_from_document,
    runtime_to_document,
)
from ada_command_center.processes.alarms_materialization.job import (
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
    AlarmMaterializationSupersededError,
)
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublicationError,
    AlarmMaterializationPublisher,
    CosmosAlarmMaterializationResultStore,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationError,
    AlarmQualificationEvidence,
    JsonFileAlarmQualificationProvider,
)
from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE_KEY = SourceKey('alarm-configuration')
_PUBLISHED = datetime(2026, 9, 26, 12, tzinfo=UTC)


def _record(revision='alarm-r10'):
    return ProjectionRecord(
        source_key=_SOURCE_KEY,
        source_release_id=SourceReleaseId(revision),
        source_published_at_utc=_PUBLISHED,
        projected_at_utc=_PUBLISHED + timedelta(minutes=1),
        payload=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='catalog-c5', tools=()
            ),
        ),
    )


class _Projection:
    def __init__(self, record=None):
        self.record = record or _record()
        self.calls = 0
        self.second = None

    def get_active(self, source_key):
        assert source_key == _SOURCE_KEY
        self.calls += 1
        return self.second if self.calls == 2 and self.second is not None else self.record


class _Client:
    def __init__(self):
        self.items = {}
        self.writes = 0
        self.fail = False

    def find_item(self, *, container_name, item_id, partition_key):
        return self.items.get((container_name, item_id, partition_key))

    def create_item(self, *, container_name, item):
        self.writes += 1
        if self.fail:
            raise CosmosError('Storage unavailable')
        key = (container_name, item['id'], item['partition_key'])
        if key in self.items:
            raise CosmosConflictError('Already exists')
        self.items[key] = dict(item)
        return dict(item)


class _Context:
    def __init__(self):
        self.facts = {}
        self.work = 0
        self.fences = 0

    def raise_if_cancelled(self):
        pass

    def assert_lease_current(self):
        pass

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield

    def mark_iteration_work(self):
        self.work += 1

    def set_iteration_fact(self, key, value):
        self.facts[key] = value


def _evidence(revision='alarm-r10', *, qualified_at='2026-09-26T12:02:00+00:00'):
    return AlarmQualificationEvidence.from_document(
        {
            'schema_version': 1,
            'source_key': _SOURCE_KEY.value,
            'source_release_id': revision,
            'source_published_at_utc': _PUBLISHED.isoformat(),
            'confirmed_tool_catalog_revision': 'catalog-c5',
            'qualified_at_utc': qualified_at,
            'producer': 'controlled-qualification-test',
            'evidence_ref': 'qualification-run-1',
            'green_tool_keys': [],
            'qualified_evaluators': [],
        }
    )


class _Qualifications:
    def __init__(self, evidence):
        self.evidence = evidence
        self.next_evidence = None
        self.calls = 0

    def load(self, candidate):
        self.calls += 1
        return (
            self.next_evidence
            if self.calls == 2 and self.next_evidence is not None
            else self.evidence
        )


def _job(projection=None, provider=None, client=None):
    projection = projection or _Projection()
    provider = provider or _Qualifications(_evidence())
    client = client or _Client()
    publisher = AlarmMaterializationPublisher(
        CosmosAlarmMaterializationResultStore(client=client, container_name='materialized-alarms')
    )
    return (
        AlarmMaterializationJob(
            acquirer=AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY),
            qualifications=provider,
            publisher=publisher,
        ),
        projection,
        provider,
        client,
        publisher,
    )


def _ready(key=None):
    key = key or AlarmResolutionKey('alarm-r10', 'catalog-c5')
    return AlarmConfigurationResolution(
        resolution_key=key,
        status=AlarmResolutionStatus.READY,
        findings=(),
        runtime_configuration=RuntimeAlarmConfiguration(
            resolution_key=key,
            defined_alarm_identities=(),
            planned_alarms=(),
            parameters_by_alarm={},
        ),
        delivery_configuration=DeliveryAlarmConfiguration(resolution_key=key, alarms=()),
    )


def test_ready_cycle_publishes_one_atomic_document_and_exact_reader():
    job, _, _, client, publisher = _job()
    context = _Context()

    result = job.run_iteration(context)

    assert result.outcome is AlarmMaterializationOutcome.READY
    assert context.work == 1
    assert context.fences == 1
    assert client.writes == 1
    stored = next(iter(client.items.values()))
    assert stored['status'] == 'READY'
    assert stored['runtime'] is not None and stored['delivery'] is not None
    assert stored['manifest']['source_release_id'] == 'alarm-r10'
    assert stored['manifest']['confirmed_tool_catalog_revision'] == 'catalog-c5'
    restored = publisher.read_ready(source_key=_SOURCE_KEY.value, result_id=result.result_id)
    assert restored.runtime == _ready().runtime_configuration
    assert restored.delivery == _ready().delivery_configuration
    assert restored.manifest['qualification_producer'] == 'controlled-qualification-test'


def test_same_candidate_and_qualification_is_idempotent():
    job, _, _, client, _ = _job()
    first = job.run_iteration(_Context())
    context = _Context()

    second = job.run_iteration(context)

    assert second.outcome is AlarmMaterializationOutcome.UNCHANGED
    assert first.result_id == second.result_id
    assert client.writes == 1
    assert context.work == 0 and context.fences == 0


def test_different_qualification_attestation_creates_separate_result():
    provider = _Qualifications(_evidence())
    job, _, _, client, _ = _job(provider=provider)
    first = job.run_iteration(_Context())
    provider.evidence = _evidence(qualified_at='2026-09-26T12:03:00+00:00')
    provider.calls = 0

    second = job.run_iteration(_Context())

    assert second.outcome is AlarmMaterializationOutcome.READY
    assert first.result_id != second.result_id
    assert len(client.items) == 2


def test_evidence_for_different_release_fails_closed():
    job, _, _, client, _ = _job(provider=_Qualifications(_evidence('alarm-r9')))

    with pytest.raises(AlarmQualificationError, match='does not match'):
        job.run_iteration(_Context())

    assert client.writes == 0


def test_projection_switch_during_materialization_never_publishes():
    projection = _Projection()
    projection.second = _record('alarm-r11')
    job, _, _, client, _ = _job(projection=projection)

    from ada_command_center.processes.alarms_materialization.errors import (
        AlarmCandidateMismatchError,
    )

    with pytest.raises((AlarmCandidateMismatchError, AlarmMaterializationSupersededError)):
        job.run_iteration(_Context())

    assert client.writes == 0


def test_evidence_change_during_materialization_never_publishes():
    provider = _Qualifications(_evidence())
    provider.next_evidence = _evidence(qualified_at='2026-09-26T12:04:00+00:00')
    job, _, _, client, _ = _job(provider=provider)

    with pytest.raises(AlarmQualificationError, match='changed'):
        job.run_iteration(_Context())

    assert client.writes == 0


def test_blocked_result_keeps_findings_without_runtime_artifacts(monkeypatch):
    import ada_command_center.processes.alarms_materialization.job as job_module

    def blocked(**kwargs):
        key = AlarmResolutionKey(
            kwargs['alarm_configuration_revision'], kwargs['confirmed_tool_catalog'].revision
        )
        return AlarmConfigurationResolution(
            resolution_key=key,
            status=AlarmResolutionStatus.BLOCKED,
            findings=(
                AlarmResolutionFinding(
                    code='evaluator_not_qualified',
                    severity=AlarmResolutionFindingSeverity.BLOCKING,
                    message='Evaluator is not qualified',
                ),
            ),
        )

    monkeypatch.setattr(job_module, 'resolve_alarm_configuration', blocked)
    job, _, _, client, publisher = _job()

    result = job.run_iteration(_Context())

    assert result.outcome is AlarmMaterializationOutcome.BLOCKED
    stored = next(iter(client.items.values()))
    assert stored['status'] == 'BLOCKED'
    assert stored['runtime'] is None and stored['delivery'] is None
    assert stored['findings'][0]['code'] == 'evaluator_not_qualified'
    with pytest.raises(AlarmMaterializationPublicationError, match='unavailable'):
        publisher.read_ready(source_key=_SOURCE_KEY.value, result_id=result.result_id)


def test_failed_storage_never_creates_ready_result():
    client = _Client()
    client.fail = True
    job, _, _, client, _ = _job(client=client)

    with pytest.raises(AlarmMaterializationPublicationError, match='publish'):
        job.run_iteration(_Context())

    assert client.items == {}


def test_checksum_corruption_blocks_ready_reader():
    job, _, _, client, publisher = _job()
    result = job.run_iteration(_Context())
    item = next(iter(client.items.values()))
    item['runtime']['defined_alarm_identities'].append({'family_key': 'extra', 'alarm_key': 'a'})

    with pytest.raises(AlarmMaterializationPublicationError, match='integrity'):
        publisher.read_ready(source_key=_SOURCE_KEY.value, result_id=result.result_id)


def test_existing_content_conflict_cannot_be_silently_overwritten():
    job, _, _, client, _ = _job()
    job.run_iteration(_Context())
    item = next(iter(client.items.values()))
    item['manifest']['source_release_id'] = 'tampered'

    with pytest.raises(AlarmMaterializationPublicationError):
        job.run_iteration(_Context())
    assert client.writes == 1


def test_qualification_file_must_match_candidate(tmp_path):
    _, projection, _, _, _ = _job()
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY).acquire()
    source = tmp_path / 'qualification.json'
    import json

    source.write_text(json.dumps(_evidence().to_document()), encoding='utf-8')
    provider = JsonFileAlarmQualificationProvider(source)
    assert provider.load(candidate).digest == _evidence().digest
    document = _evidence('alarm-r9').to_document()
    source.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(AlarmQualificationError):
        provider.load(candidate)


def test_codec_recovers_nonempty_runtime_and_delivery_contracts():
    key = AlarmResolutionKey('alarm-r10', 'catalog-c5')
    identity = AlarmIdentity(family_key='family-a', alarm_key='alarm-a')
    runtime = RuntimeAlarmConfiguration(
        resolution_key=key,
        defined_alarm_identities=(identity,),
        planned_alarms=(
            PlannedAlarm(
                identity=identity,
                kind=AlarmKind.IMPACT,
                criticality=Criticality.C2,
                priority_group='priority',
                priority_order=1,
                evaluator_key='evaluator-a',
                alarm_configuration_revision='alarm-r10',
                tool_registry_revision='catalog-c5',
                routing=AlarmRouting(
                    origin_tool_key='process-a',
                    destinations=(RoutingDestination(tool_key='integrated-b', delay_seconds=1200),),
                ),
                deactivation_policy=DeactivationPolicy(approval_required=True),
                reappearance_after_seconds=300,
                reappearance_special_conditions=(),
            ),
        ),
        parameters_by_alarm={identity: {'threshold': 10.5, 'enabled': True, 'label': 'A'}},
    )
    delivery = DeliveryAlarmConfiguration(
        resolution_key=key,
        alarms=(
            ResolvedDeliveryAlarm(
                identity=identity,
                is_active=True,
                visibility_mode=VisibilityMode.VISIBLE,
                display_name='Alarm A',
                title='A title',
                cause_template='A cause',
                kind=AlarmKind.IMPACT,
                criticality=Criticality.C2,
                business_category=BusinessCategory.PRODUCTIVITY,
                operational_areas=(OperationalArea.MINE,),
                color=AlarmColor.RED,
                default_deactivation_policy=ResolvedDeactivationPolicy(
                    enabled=True, max_duration_hours=3, approval_required=True
                ),
                messages=(
                    ResolvedDeliveryMessage(
                        message_key='msg-a',
                        display_text='A message',
                        deactivation_policy=ResolvedDeactivationPolicy(
                            enabled=False, max_duration_hours=None, approval_required=False
                        ),
                    ),
                ),
                visual_targets=(
                    ResolvedVisualTarget(
                        tool_key='process-a',
                        tool_kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                        component_keys=('mine',),
                        subcomponents=(
                            ResolvedVisualSubcomponentTarget(
                                owner_component_key='mine', subcomponent_key='crusher'
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    restored_runtime = runtime_from_document(runtime_to_document(runtime))
    restored_delivery = delivery_from_document(delivery_to_document(delivery))

    assert restored_runtime.resolution_key == runtime.resolution_key
    assert restored_runtime.planned_alarms == runtime.planned_alarms
    assert dict(restored_runtime.parameters_by_alarm[identity]) == dict(
        runtime.parameters_by_alarm[identity]
    )
    assert restored_delivery == delivery


def test_module_entrypoint_delegates_to_bootstrap(monkeypatch):
    import runpy

    import ada_command_center.processes.alarms_materialization.bootstrap as bootstrap

    calls = []
    monkeypatch.setattr(bootstrap, 'main', lambda: calls.append('executed'))

    runpy.run_module(
        'ada_command_center.processes.alarms_materialization.__main__',
        run_name='__main__',
    )

    assert calls == ['executed']


def test_concurrent_same_result_create_is_idempotent():
    job, _, _, client, _ = _job()

    def concurrent_create(*, container_name, item):
        client.items[(container_name, item['id'], item['partition_key'])] = dict(item)
        raise CosmosConflictError('Concurrent writer created the same result')

    client.create_item = concurrent_create

    result = job.run_iteration(_Context())

    assert result.outcome is AlarmMaterializationOutcome.READY
    assert len(client.items) == 1


def test_missing_qualification_file_fails_without_inferred_green(tmp_path):
    _, projection, _, _, _ = _job()
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY).acquire()
    with pytest.raises(AlarmQualificationError, match='Could not load'):
        JsonFileAlarmQualificationProvider(tmp_path / 'not-present.json').load(candidate)
