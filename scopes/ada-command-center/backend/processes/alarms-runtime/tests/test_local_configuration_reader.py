import json
from hashlib import sha256

import pytest

from ada_command_center.alarms.materialization.local_reader import (
    AlarmMaterializationPublicationError,
    materialization_result_id,
    materialization_root,
)
from ada_command_center.processes.alarms_runtime.local_configuration import (
    RuntimeLocalConfigurationReader,
)

_SOURCE = 'alarm-configuration'


def _write_json(path, document):
    payload = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(',', ':')
    ).encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {'sha256': sha256(payload).hexdigest(), 'size_bytes': len(payload)}


def _publish_fixture(
    volume,
    *,
    release='alarm-r10',
    tool_revision='catalog-c5',
    qualification_digest='b' * 64,
    status='READY',
    promote=True,
):
    root = materialization_root(volume)
    resolution_key = {
        'alarm_configuration_revision': release,
        'confirmed_tool_catalog_revision': tool_revision,
    }
    projection_digest = 'a' * 64
    result_id = materialization_result_id(
        source_key=_SOURCE,
        projection_digest=projection_digest,
        qualification_digest=qualification_digest,
    )
    version = root / 'versions' / result_id
    version.mkdir(parents=True, exist_ok=True)
    runtime = {
        'resolution_key': resolution_key,
        'defined_alarm_identities': [],
        'planned_alarms': [],
        'parameters_by_alarm': [],
    }
    delivery = {'resolution_key': resolution_key, 'alarms': []}
    inventory = {}
    if status == 'READY':
        for label, document in (('runtime', runtime), ('delivery', delivery)):
            info = _write_json(version / f'{label}.json', document)
            inventory[label] = {'path': f'{label}.json', **info}
    manifest = {
        'document_type': 'ada_command_center_alarm_materialization_result',
        'schema_version': 1,
        'source_key': _SOURCE,
        'result_id': result_id,
        'status': status,
        'resolution_key': resolution_key,
        'provenance': {
            'source_release_id': release,
            'source_published_at_utc': '2026-09-26T12:00:00+00:00',
            'confirmed_tool_catalog_revision': tool_revision,
            'projection_digest': projection_digest,
            'qualification_digest': qualification_digest,
            'qualification_producer': 'controlled-test',
            'qualification_evidence_ref': 'qualification-1',
            'qualified_at_utc': '2026-09-26T12:01:00+00:00',
        },
        'findings': (
            []
            if status == 'READY'
            else [
                {
                    'code': 'tool_reference_not_green',
                    'severity': 'BLOCKING',
                    'message': 'Tool is not green',
                    'alarm_identity': None,
                    'field_path': None,
                    'reference_key': None,
                }
            ]
        ),
        'artifacts': inventory,
    }
    manifest_hash = _write_json(version / 'manifest.json', manifest)['sha256']
    if promote:
        _write_json(
            root / 'ready.json',
            {
                'document_type': 'ada_command_center_alarm_materialization_ready',
                'schema_version': 1,
                'source_key': _SOURCE,
                'result_id': result_id,
                'resolution_key': resolution_key,
                'manifest_sha256': manifest_hash,
            },
        )
    return version, result_id, manifest_hash


def test_runtime_reads_one_valid_ready_pair_without_adopting(tmp_path):
    _, result_id, digest = _publish_fixture(tmp_path)
    head = materialization_root(tmp_path) / 'ready.json'
    before = head.read_bytes()

    candidate = RuntimeLocalConfigurationReader(
        volume_path=tmp_path, source_key=_SOURCE
    ).load_ready_candidate()

    assert candidate.result_id == result_id
    assert candidate.manifest_sha256 == digest
    assert candidate.runtime.resolution_key == candidate.delivery.resolution_key
    assert candidate.runtime.resolution_key.alarm_configuration_revision == 'alarm-r10'
    assert head.read_bytes() == before
    assert not (materialization_root(tmp_path) / 'effective.json').exists()


def test_runtime_exact_read_is_pinned_not_latest(tmp_path):
    _, old_id, old_hash = _publish_fixture(tmp_path)
    _, new_id, _ = _publish_fixture(
        tmp_path,
        release='alarm-r11',
        qualification_digest='c' * 64,
    )
    reader = RuntimeLocalConfigurationReader(volume_path=tmp_path, source_key=_SOURCE)

    old = reader.load_exact_candidate(result_id=old_id, manifest_sha256=old_hash)
    latest = reader.load_ready_candidate()

    assert old.result_id == old_id
    assert latest.result_id == new_id
    assert old.runtime.resolution_key.alarm_configuration_revision == 'alarm-r10'
    assert latest.runtime.resolution_key.alarm_configuration_revision == 'alarm-r11'


def test_runtime_no_ready_head_does_not_select_historic_version(tmp_path):
    _publish_fixture(tmp_path, promote=False)
    candidate = RuntimeLocalConfigurationReader(
        volume_path=tmp_path, source_key=_SOURCE
    ).load_ready_candidate()
    assert candidate is None


def test_runtime_rejects_head_targeting_blocked(tmp_path):
    _publish_fixture(tmp_path, status='BLOCKED')
    reader = RuntimeLocalConfigurationReader(volume_path=tmp_path, source_key=_SOURCE)
    with pytest.raises(AlarmMaterializationPublicationError, match='unavailable'):
        reader.load_ready_candidate()


def test_runtime_does_not_fallback_when_head_artifact_corrupt(tmp_path):
    _publish_fixture(tmp_path)
    current, _, _ = _publish_fixture(
        tmp_path,
        release='alarm-r11',
        qualification_digest='c' * 64,
    )
    (current / 'delivery.json').write_text('{"tampered":true}', encoding='utf-8')
    reader = RuntimeLocalConfigurationReader(volume_path=tmp_path, source_key=_SOURCE)
    with pytest.raises(AlarmMaterializationPublicationError, match='integrity'):
        reader.load_ready_candidate()


def test_runtime_rejects_wrong_source_and_manifest_hash(tmp_path):
    _, result_id, digest = _publish_fixture(tmp_path)
    with pytest.raises(AlarmMaterializationPublicationError, match='pointer'):
        RuntimeLocalConfigurationReader(
            volume_path=tmp_path,
            source_key='other-source',
        ).load_ready_candidate()
    with pytest.raises(AlarmMaterializationPublicationError, match='integrity'):
        RuntimeLocalConfigurationReader(
            volume_path=tmp_path, source_key=_SOURCE
        ).load_exact_candidate(result_id=result_id, manifest_sha256='f' * 64)
    assert len(digest) == 64


def test_runtime_rejects_path_injection_in_exact_version(tmp_path):
    with pytest.raises(AlarmMaterializationPublicationError, match='identity'):
        RuntimeLocalConfigurationReader(
            volume_path=tmp_path, source_key=_SOURCE
        ).load_exact_candidate(result_id='../not-allowed', manifest_sha256='f' * 64)
