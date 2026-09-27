from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
    LocalAlarmMaterializationReader,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
    RuntimeAlarmConfiguration,
    materialization_root,
)
from ada_command_center.alarms.materialization.codec import (
    delivery_from_document,
    delivery_to_document,
    runtime_from_document,
    runtime_to_document,
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
from ada_command_center.processes.alarms_materialization.errors import AlarmCandidateMismatchError
from ada_command_center.processes.alarms_materialization.job import (
    AlarmMaterializationJob,
    AlarmMaterializationOutcome,
    AlarmMaterializationSupersededError,
)
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublicationError,
    AlarmMaterializationPublisher,
    LocalAlarmMaterializationResultStore,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationError,
    AlarmQualificationEvidence,
    JsonFileAlarmQualificationProvider,
)
from atlanticus.state import StateWriteError
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


def _job(tmp_path, projection=None, provider=None, store=None):
    projection = projection or _Projection()
    provider = provider or _Qualifications(_evidence())
    store = store or LocalAlarmMaterializationResultStore(root=tmp_path / 'materialization')
    publisher = AlarmMaterializationPublisher(store)
    return (
        AlarmMaterializationJob(
            acquirer=AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY),
            qualifications=provider,
            publisher=publisher,
        ),
        projection,
        provider,
        store,
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


def _version_root(tmp_path, result_id):
    return tmp_path / 'materialization' / 'versions' / result_id


def test_ready_cycle_publishes_coherent_artifacts_and_exact_reader(tmp_path):
    job, _, _, store, publisher = _job(tmp_path)
    context = _Context()

    result = job.run_iteration(context)

    assert result.outcome is AlarmMaterializationOutcome.READY
    assert context.work == 1 and context.fences == 1
    version = _version_root(tmp_path, result.result_id)
    assert sorted(path.name for path in version.iterdir()) == [
        'delivery.json',
        'manifest.json',
        'runtime.json',
    ]
    stored = store.get(source_key=_SOURCE_KEY.value, result_id=result.result_id)
    assert stored['status'] == 'READY'
    assert stored['provenance']['source_release_id'] == 'alarm-r10'
    assert stored['provenance']['confirmed_tool_catalog_revision'] == 'catalog-c5'
    restored = publisher.read_published_ready(source_key=_SOURCE_KEY.value)
    assert restored.result_id == result.result_id
    assert restored.runtime == _ready().runtime_configuration
    assert restored.delivery == _ready().delivery_configuration
    assert restored.manifest['provenance']['qualification_producer'] == (
        'controlled-qualification-test'
    )
    exact = publisher.read_ready(
        source_key=_SOURCE_KEY.value,
        result_id=result.result_id,
        expected_manifest_sha256=restored.manifest_sha256,
    )
    assert exact == restored


def test_same_candidate_is_idempotent_without_new_mutation(tmp_path):
    job, _, _, _, _ = _job(tmp_path)
    first = job.run_iteration(_Context())
    context = _Context()

    second = job.run_iteration(context)

    assert second.outcome is AlarmMaterializationOutcome.UNCHANGED
    assert first.result_id == second.result_id
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 1
    assert context.work == 0 and context.fences == 0


def test_changed_qualification_produces_distinct_version_with_shared_resolution_key(tmp_path):
    provider = _Qualifications(_evidence())
    job, _, _, store, _ = _job(tmp_path, provider=provider)
    first = job.run_iteration(_Context())
    provider.evidence = _evidence(qualified_at='2026-09-26T12:03:00+00:00')
    provider.calls = 0

    second = job.run_iteration(_Context())

    assert second.result_id != first.result_id
    assert second.outcome is AlarmMaterializationOutcome.READY
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 2
    assert store.read_published_ready(source_key=_SOURCE_KEY.value).result_id == second.result_id
    assert (
        store.read_ready(
            source_key=_SOURCE_KEY.value, result_id=first.result_id
        ).runtime.resolution_key
        == store.read_ready(
            source_key=_SOURCE_KEY.value, result_id=second.result_id
        ).runtime.resolution_key
    )


def test_qualification_for_different_release_fails_closed(tmp_path):
    job, _, _, _, publisher = _job(tmp_path, provider=_Qualifications(_evidence('alarm-r9')))
    with pytest.raises(AlarmQualificationError, match='does not match'):
        job.run_iteration(_Context())
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value) is None


def test_projection_switch_during_resolution_never_publishes(tmp_path):
    projection = _Projection()
    projection.second = _record('alarm-r11')
    job, _, _, _, publisher = _job(tmp_path, projection=projection)
    with pytest.raises((AlarmCandidateMismatchError, AlarmMaterializationSupersededError)):
        job.run_iteration(_Context())
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value) is None


def test_evidence_change_during_resolution_never_publishes(tmp_path):
    provider = _Qualifications(_evidence())
    provider.next_evidence = _evidence(qualified_at='2026-09-26T12:04:00+00:00')
    job, _, _, _, publisher = _job(tmp_path, provider=provider)
    with pytest.raises(AlarmQualificationError, match='changed'):
        job.run_iteration(_Context())
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value) is None


def test_blocked_diagnostics_do_not_replace_previous_ready(monkeypatch, tmp_path):
    import ada_command_center.processes.alarms_materialization.job as job_module

    job, projection, provider, store, publisher = _job(tmp_path)
    previous = job.run_iteration(_Context())
    projection.record = _record('alarm-r11')
    provider.evidence = _evidence('alarm-r11')

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
    blocked_result = job.run_iteration(_Context())

    assert blocked_result.outcome is AlarmMaterializationOutcome.BLOCKED
    manifest = store.get(source_key=_SOURCE_KEY.value, result_id=blocked_result.result_id)
    assert manifest['status'] == 'BLOCKED'
    assert manifest['artifacts'] == {}
    assert manifest['findings'][0]['code'] == 'evaluator_not_qualified'
    assert sorted(
        path.name for path in _version_root(tmp_path, blocked_result.result_id).iterdir()
    ) == ['manifest.json']
    assert (
        publisher.read_published_ready(source_key=_SOURCE_KEY.value).result_id == previous.result_id
    )
    with pytest.raises(AlarmMaterializationPublicationError, match='unavailable'):
        publisher.read_ready(source_key=_SOURCE_KEY.value, result_id=blocked_result.result_id)


def test_failed_version_staging_does_not_publish_ready(monkeypatch, tmp_path):
    import ada_command_center.processes.alarms_materialization.publication as publication

    job, _, _, _, publisher = _job(tmp_path)

    def fail_rename(*args):
        raise OSError('Injected directory promotion failure')

    monkeypatch.setattr(publication.os, 'rename', fail_rename)
    with pytest.raises(AlarmMaterializationPublicationError, match='publish'):
        job.run_iteration(_Context())
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value) is None
    assert list((tmp_path / 'materialization' / 'versions').iterdir()) == []


@pytest.mark.parametrize('filename', ['runtime.json', 'delivery.json', 'manifest.json'])
def test_partial_artifact_write_never_exposes_ready(monkeypatch, tmp_path, filename):
    from atlanticus.state import AtomicJsonStore

    job, _, _, store, _ = _job(tmp_path)
    original = AtomicJsonStore.replace

    def fail_selected(self, relative_path, value):
        if relative_path == filename:
            raise StateWriteError('Injected artifact write failure')
        return original(self, relative_path, value)

    with monkeypatch.context() as patch:
        patch.setattr(AtomicJsonStore, 'replace', fail_selected)
        with pytest.raises(AlarmMaterializationPublicationError, match='publish'):
            job.run_iteration(_Context())

    assert store.read_published_ready(source_key=_SOURCE_KEY.value) is None
    assert list((tmp_path / 'materialization' / 'versions').iterdir()) == []


def test_failed_ready_pointer_can_recover_committed_version(monkeypatch, tmp_path):
    from atlanticus.state import AtomicJsonStore

    job, _, _, _, publisher = _job(tmp_path)
    original = AtomicJsonStore.replace

    def fail_ready(self, relative_path, value):
        if relative_path == 'ready.json':
            raise StateWriteError('Injected pointer promotion failure')
        return original(self, relative_path, value)

    with monkeypatch.context() as patch:
        patch.setattr(AtomicJsonStore, 'replace', fail_ready)
        with pytest.raises(AlarmMaterializationPublicationError, match='promote'):
            job.run_iteration(_Context())
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value) is None
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 1

    context = _Context()
    recovered = job.run_iteration(context)

    assert recovered.outcome is AlarmMaterializationOutcome.READY
    assert context.work == 1 and context.fences == 1
    assert publisher.read_published_ready(source_key=_SOURCE_KEY.value).result_id == (
        recovered.result_id
    )


def test_existing_valid_version_can_be_promoted_after_reversion(tmp_path):
    job, projection, provider, store, _ = _job(tmp_path)
    first = job.run_iteration(_Context())
    projection.record = _record('alarm-r11')
    provider.evidence = _evidence('alarm-r11')
    second = job.run_iteration(_Context())
    projection.record = _record('alarm-r10')
    provider.evidence = _evidence()
    context = _Context()

    reverted = job.run_iteration(context)

    assert reverted.outcome is AlarmMaterializationOutcome.READY
    assert reverted.result_id == first.result_id != second.result_id
    assert store.read_published_ready(source_key=_SOURCE_KEY.value).result_id == first.result_id
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 2
    assert context.work == 1 and context.fences == 1


def test_reversion_does_not_promote_if_projection_changed_during_revalidation(tmp_path):
    job, projection, provider, store, _ = _job(tmp_path)
    first = job.run_iteration(_Context())
    projection.record = _record('alarm-r11')
    provider.evidence = _evidence('alarm-r11')
    second = job.run_iteration(_Context())
    projection.record = _record('alarm-r10')
    projection.second = _record('alarm-r12')
    projection.calls = 0
    provider.evidence = _evidence()

    with pytest.raises((AlarmCandidateMismatchError, AlarmMaterializationSupersededError)):
        job.run_iteration(_Context())
    assert first.result_id != second.result_id
    assert store.read_published_ready(source_key=_SOURCE_KEY.value).result_id == second.result_id


@pytest.mark.parametrize('artifact', ['runtime.json', 'delivery.json'])
def test_corrupt_runtime_artifact_is_rejected_without_fallback(tmp_path, artifact):
    job, _, _, store, _ = _job(tmp_path)
    result = job.run_iteration(_Context())
    runtime_path = _version_root(tmp_path, result.result_id) / artifact
    runtime_path.write_bytes(runtime_path.read_bytes() + b' ')

    with pytest.raises(AlarmMaterializationPublicationError, match='integrity'):
        store.read_published_ready(source_key=_SOURCE_KEY.value)


def test_exact_reader_rejects_incorrect_manifest_digest(tmp_path):
    job, _, _, store, _ = _job(tmp_path)
    result = job.run_iteration(_Context())

    with pytest.raises(AlarmMaterializationPublicationError, match='manifest integrity'):
        store.read_ready(
            source_key=_SOURCE_KEY.value,
            result_id=result.result_id,
            expected_manifest_sha256='0' * 64,
        )


def test_pointer_rejects_different_source_key(tmp_path):
    job, _, _, store, _ = _job(tmp_path)
    job.run_iteration(_Context())

    with pytest.raises(AlarmMaterializationPublicationError, match='pointer'):
        store.read_published_ready(source_key='another-source')


def test_modified_manifest_is_rejected_by_pointer_digest(tmp_path):
    job, _, _, store, _ = _job(tmp_path)
    result = job.run_iteration(_Context())
    manifest_path = _version_root(tmp_path, result.result_id) / 'manifest.json'
    manifest_path.write_bytes(manifest_path.read_bytes() + b' ')

    with pytest.raises(AlarmMaterializationPublicationError, match='manifest integrity'):
        store.read_published_ready(source_key=_SOURCE_KEY.value)


def test_uncommitted_orphan_stage_is_recovered_on_retry(tmp_path):
    job, projection, _, store, _ = _job(tmp_path)
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY).acquire()
    evidence = _evidence()
    from ada_command_center.processes.alarms_materialization.publication import result_id_for

    identifier = result_id_for(candidate, evidence)
    orphan = tmp_path / 'materialization' / 'versions' / f'.{identifier}.stale.staging'
    orphan.mkdir(parents=True)
    (orphan / 'runtime.json').write_text('incomplete', encoding='utf-8')

    result = job.run_iteration(_Context())

    assert result.result_id == identifier
    assert not orphan.exists()
    assert store.read_published_ready(source_key=_SOURCE_KEY.value).result_id == identifier


def test_failure_during_new_version_preserves_old_ready(monkeypatch, tmp_path):
    import ada_command_center.processes.alarms_materialization.publication as publication

    job, projection, provider, store, _ = _job(tmp_path)
    first = job.run_iteration(_Context())
    projection.record = _record('alarm-r11')
    provider.evidence = _evidence('alarm-r11')
    with monkeypatch.context() as patch:
        patch.setattr(
            publication.os,
            'rename',
            lambda *args: (_ for _ in ()).throw(OSError('Injected rename failure')),
        )
        with pytest.raises(AlarmMaterializationPublicationError, match='publish'):
            job.run_iteration(_Context())

    assert store.read_published_ready(source_key=_SOURCE_KEY.value).result_id == first.result_id
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 1


def test_existing_content_conflict_is_not_silently_overwritten(tmp_path):
    job, _, _, store, _ = _job(tmp_path)
    first = job.run_iteration(_Context())
    manifest_path = _version_root(tmp_path, first.result_id) / 'manifest.json'
    manifest = manifest_path.read_text(encoding='utf-8')
    manifest_path.write_text(
        manifest.replace('controlled-qualification-test', 'tampered'), encoding='utf-8'
    )

    with pytest.raises(AlarmMaterializationPublicationError):
        job.run_iteration(_Context())
    assert len(list((tmp_path / 'materialization' / 'versions').iterdir())) == 1
    with pytest.raises(AlarmMaterializationPublicationError):
        store.read_published_ready(source_key=_SOURCE_KEY.value)


def test_qualification_file_must_match_candidate(tmp_path):
    _, projection, _, _, _ = _job(tmp_path)
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY).acquire()
    import json

    source = tmp_path / 'qualification.json'
    source.write_text(json.dumps(_evidence().to_document()), encoding='utf-8')
    provider = JsonFileAlarmQualificationProvider(source)
    assert provider.load(candidate).digest == _evidence().digest
    source.write_text(json.dumps(_evidence('alarm-r9').to_document()), encoding='utf-8')
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
        'ada_command_center.processes.alarms_materialization.__main__', run_name='__main__'
    )
    assert calls == ['executed']


def test_missing_qualification_file_fails_without_inferred_green(tmp_path):
    _, projection, _, _, _ = _job(tmp_path)
    candidate = AlarmCandidateAcquirer(projection=projection, source_key=_SOURCE_KEY).acquire()
    with pytest.raises(AlarmQualificationError, match='Could not load'):
        JsonFileAlarmQualificationProvider(tmp_path / 'not-present.json').load(candidate)


def test_composition_validates_only_cosmos_projection_input(monkeypatch):
    import ada_command_center.processes.alarms_materialization.composition as module

    inspected = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Provisioner:
        def __init__(self, *, client):
            assert isinstance(client, Client)

        def validate_containers(self, specs):
            inspected.extend(specs)

    monkeypatch.setattr(module, 'CosmosProvisioner', Provisioner)
    monkeypatch.setattr(module, 'execute_job', lambda **kwargs: 'executed')
    composition = module.AlarmMaterializationComposition(
        configuration=SimpleNamespace(values={}),
        settings=SimpleNamespace(projection_container='alarm-projection'),
        cosmos=Client(),
        job=SimpleNamespace(run_iteration=lambda context: None),
        definition=object(),
    )

    assert composition.execute() == 'executed'
    assert len(inspected) == 1
    assert inspected[0].name == 'alarm-projection'
    assert inspected[0].partition_key_path == '/partition_key'


def test_shared_reader_can_independently_consume_published_pair(tmp_path):
    store = LocalAlarmMaterializationResultStore(root=materialization_root(tmp_path))
    job, _, _, _, _ = _job(tmp_path, store=store)
    result = job.run_iteration(_Context())
    reader = LocalAlarmMaterializationReader(root=materialization_root(tmp_path))

    ready = reader.read_published_ready(source_key=_SOURCE_KEY.value)
    exact = reader.read_exact_ready(
        source_key=_SOURCE_KEY.value,
        result_id=ready.result_id,
        manifest_sha256=ready.manifest_sha256,
    )

    assert ready.result_id == result.result_id
    assert exact == ready
    assert ready.runtime.resolution_key == ready.delivery.resolution_key
