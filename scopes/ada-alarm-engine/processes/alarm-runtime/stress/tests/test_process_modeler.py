from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ada.alarms.materialization import engine_from_document, materialization_result_id
from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from stress.run_process_modeler import ALARM_COUNT, PROCESS_TOOL, create_fixture, install_fixture


def _root() -> Path:
    return Path(__file__).resolve().parents[1] / 'fixtures'


@pytest.mark.parametrize('distributed', (0, 1, 2))
def test_process_fixture_is_coherent_and_loadable(tmp_path, distributed):
    payloads = create_fixture(fixture_root=_root(), distributed_count=distributed)
    ready = json.loads(payloads['ready.json'])
    manifest = json.loads(payloads['manifest.json'])
    engine = json.loads(payloads['engine.json'])
    modeler = json.loads(payloads['modeler.json'])
    delivery = json.loads(payloads['delivery.json'])
    assert ready['manifest_sha256'] == hashlib.sha256(payloads['manifest.json']).hexdigest()
    assert ready['result_id'] == manifest['result_id']
    assert manifest['result_id'] == materialization_result_id(
        source_key='alarm-configuration',
        projection_digest=manifest['provenance']['projection_digest'],
    )
    for name in ('engine', 'modeler', 'delivery'):
        blob = payloads[name + '.json']
        assert manifest['artifacts'][name]['sha256'] == hashlib.sha256(blob).hexdigest()
        assert manifest['artifacts'][name]['size_bytes'] == len(blob)
    assert engine['resolution_key'] == modeler['resolution_key'] == delivery['resolution_key']
    assert len(engine_from_document(engine).planned_alarms) == ALARM_COUNT
    assert len(modeler['alarms']) == ALARM_COUNT
    assert delivery['publication_tool_keys'] == [PROCESS_TOOL]
    assert (
        sum(
            row['visual_targets'][0]['process_projection_mode'] == 'DISTRIBUTED'
            for row in modeler['alarms']
        )
        == distributed
    )
    assert all(row['visual_targets'][0]['tool_kind'] == 'process' for row in modeler['alarms'])
    assert len({item['priority_group'] for item in engine['planned_alarms']}) == ALARM_COUNT
    root = tmp_path / 'runtime'
    install_fixture(root=root, payloads=payloads)
    materialization = LocalAlarmMaterializationStore(root=materialization_root(root))
    published = materialization.read_published_ready(source_key='alarm-configuration')
    assert published.result_id == ready['result_id']
    published_engine = materialization.read_published_engine(source_key='alarm-configuration')
    assert len(published_engine.planned_alarms) == ALARM_COUNT


def test_rejects_unsupported_distributed_count():
    with pytest.raises(ValueError, match='0, 1, or 2'):
        create_fixture(fixture_root=_root(), distributed_count=3)
