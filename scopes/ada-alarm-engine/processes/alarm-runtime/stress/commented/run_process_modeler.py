from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ada.alarms.materialization import engine_from_document, materialization_result_id
from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.processes.alarm_runtime.bootstrap import load_configuration
from ada.processes.alarm_runtime.composition import build_composition
from ada.processes.alarm_runtime.session import build_alarm_execution_session
from stress.run_synthetic import build_registry

SOURCE_KEY = 'alarm-configuration'
PROCESS_TOOL = 'tool-process-m21-qualification'
ALARM_COUNT = 8


# Mantener la serialización estable para calcular tamaño y huella de cada artefacto.
def _serialize(document: dict) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False
        ).encode('utf-8')
        + b'\n'
    )


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# Generar una versión aislada de materialización con 8 alarmas de Process.
def create_fixture(*, fixture_root: Path, distributed_count: int) -> dict[str, bytes]:
    if distributed_count not in (0, 1, 2):
        raise ValueError('Distributed alarm count must be 0, 1, or 2')
    engine_base = json.loads((fixture_root / 'engine.json').read_text(encoding='utf-8'))
    modeler_base = json.loads((fixture_root / 'modeler.json').read_text(encoding='utf-8'))
    manifest_base = json.loads((fixture_root / 'manifest.json').read_text(encoding='utf-8'))
    revision = _hash(f'process-m21-{distributed_count}'.encode('utf-8'))
    tool_revision = _hash(f'process-tool-m21-{distributed_count}'.encode('utf-8'))
    resolution_key = {
        'alarm_configuration_revision': revision[:40],
        'confirmed_tool_catalog_revision': tool_revision,
    }
    engine = deepcopy(engine_base)
    modeler = deepcopy(modeler_base)
    delivery = {'resolution_key': resolution_key, 'publication_tool_keys': [PROCESS_TOOL]}
    engine['resolution_key'] = resolution_key
    modeler['resolution_key'] = resolution_key
    engine['defined_alarm_identities'] = []
    engine['parameters_by_alarm'] = []
    engine['planned_alarms'] = []
    modeler['alarms'] = []
    for index in range(ALARM_COUNT):
        identity = {'family_key': 'M21_PROCESS', 'alarm_key': f'process-alarm-{index + 1:02d}'}
        group = f'process-group-{index + 1:02d}'
        evaluator = f'process-evaluator-{index + 1:02d}'
        planned = deepcopy(engine_base['planned_alarms'][0])
        planned.update(
            {
                'identity': identity,
                'evaluator_key': evaluator,
                'priority_group': group,
                'priority_order': 1,
                'alarm_configuration_revision': resolution_key['alarm_configuration_revision'],
                'tool_registry_revision': resolution_key['confirmed_tool_catalog_revision'],
            }
        )
        planned['routing'] = {'origin_tool_key': PROCESS_TOOL, 'destinations': []}
        engine['planned_alarms'].append(planned)
        engine['defined_alarm_identities'].append(identity)
        engine['parameters_by_alarm'].append({'identity': identity, 'parameters': {}})
        item = deepcopy(modeler_base['alarms'][0])
        item.update(
            {
                'identity': identity,
                'priority_group': group,
                'priority_order': 1,
                'display_name': f'Process M2.1 {index + 1:02d}',
                'title': f'Process M2.1 {index + 1:02d}',
            }
        )
        item['visual_targets'] = [
            {
                'tool_key': PROCESS_TOOL,
                'tool_kind': 'process',
                'component_keys': ['component-process-m21'],
                'subcomponents': [
                    {
                        'owner_component_key': 'component-process-m21',
                        'subcomponent_key': 'subcomponent-process-m21',
                    }
                ],
                'process_projection_mode': (
                    'DISTRIBUTED' if index < distributed_count else 'GENERIC'
                ),
            }
        ]
        modeler['alarms'].append(item)
    payloads = {
        'engine.json': _serialize(engine),
        'modeler.json': _serialize(modeler),
        'delivery.json': _serialize(delivery),
    }
    # Delegar la identidad de publicación al contrato canónico, no al hash concatenado.
    projection_digest = _hash(payloads['modeler.json'])
    result_id = materialization_result_id(
        source_key=SOURCE_KEY, projection_digest=projection_digest
    )
    manifest = deepcopy(manifest_base)
    manifest['resolution_key'] = resolution_key
    manifest['result_id'] = result_id
    manifest['findings'] = []
    manifest['provenance'].update(
        {
            'confirmed_tool_catalog_revision': resolution_key['confirmed_tool_catalog_revision'],
            'projection_digest': projection_digest,
            'source_published_at_utc': datetime.now(UTC).isoformat(),
            'source_release_id': resolution_key['alarm_configuration_revision'],
        }
    )
    for artifact in ('engine', 'modeler', 'delivery'):
        name = artifact + '.json'
        manifest['artifacts'][artifact] = {
            'path': name,
            'sha256': _hash(payloads[name]),
            'size_bytes': len(payloads[name]),
        }
    payloads['manifest.json'] = _serialize(manifest)
    payloads['ready.json'] = _serialize(
        {
            'document_type': 'ada_alarm_engine_materialization_ready',
            'schema_version': 2,
            'source_key': SOURCE_KEY,
            'result_id': result_id,
            'resolution_key': resolution_key,
            'manifest_sha256': _hash(payloads['manifest.json']),
        }
    )
    return payloads


# Publicar READY después de instalar los artefactos, y validar el puntero.
def install_fixture(*, root: Path, payloads: dict[str, bytes]) -> None:
    ready = json.loads(payloads['ready.json'])
    destination = materialization_root(root)
    version = destination / 'versions' / ready['result_id']
    version.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'engine.json', 'modeler.json', 'delivery.json'):
        (version / name).write_bytes(payloads[name])
    (destination / 'ready.json').write_bytes(payloads['ready.json'])
    published = LocalAlarmMaterializationStore(root=destination).read_published_ready(
        source_key=SOURCE_KEY
    )
    if published.result_id != ready['result_id']:
        raise ValueError('Process materialization publication verification failed')


# Ejecutar el Runtime real sobre una aplicación exclusiva para esta calificación.
def execute(*, volume: Path, application: str, distributed_count: int, seconds: float) -> dict:
    if not application.startswith('ada-alarm-engine-stress-process-m21-'):
        raise ValueError('Application must use the isolated Process M2.1 prefix')
    if '/' in application or '\\' in application or application in ('.', '..'):
        raise ValueError('Application name is invalid')
    if not math.isfinite(seconds) or seconds <= 15 or seconds > 580:
        raise ValueError('Execution seconds must be between 15 and 580')
    volume = volume.expanduser().resolve()
    root = volume / application
    if root.is_symlink() or (root.exists() and any(root.iterdir())):
        raise ValueError(f'Isolated application already contains data: {root}')
    fixture_root = Path(__file__).resolve().parent / 'fixtures'
    payloads = create_fixture(fixture_root=fixture_root, distributed_count=distributed_count)
    root.mkdir(parents=True, exist_ok=True)
    install_fixture(root=root, payloads=payloads)
    engine = engine_from_document(json.loads(payloads['engine.json']))
    started_at = datetime.now(UTC)
    registry = build_registry(
        engine=engine,
        seed=20261011,
        started_at_utc=started_at,
        random_seconds=0,
        hold_seconds=int(seconds) + 120,
    )
    publication = LocalAlarmMaterializationStore(root=materialization_root(root))
    session = build_alarm_execution_session(
        configuration=publication.read_published_engine(source_key=SOURCE_KEY),
        evaluator_registry=registry,
    )
    if (
        len(session.entries) != ALARM_COUNT
        or session.data_plan.views
        or any(entry.inputs for entry in session.entries)
    ):
        raise ValueError('Process qualification requires eight input-free alarms')
    config = {
        'ENVIRONMENT': 'local',
        'APPLICATION': application,
        'VOLUMEN_PATH': str(volume),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'synthetic-no-inputs',
        'ALARM_RUNTIME_POLL_SECONDS': '1',
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'false',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    configuration = load_configuration(
        process_root=Path(__file__).resolve().parents[1], environ=config
    )
    composition = build_composition(configuration=configuration, evaluator_registry=registry)
    composition.definition = replace(
        composition.definition,
        execution_timeout_seconds=seconds,
        iteration_summary_every=0,
    )
    result = composition.execute(argv=())
    if str(result.status).lower().split('.')[-1] != 'success':
        raise RuntimeError(f'Process Runtime execution failed: {result.status}')
    current_path = root / 'alarms/output/current/latest.json'
    if not current_path.is_file():
        raise RuntimeError('Process Runtime did not publish resolved CURRENT')
    current = json.loads(current_path.read_text(encoding='utf-8'))
    alarms = current.get('state', {}).get('alarms', [])
    if current.get('schema_version') != 1 or len(alarms) != ALARM_COUNT:
        raise RuntimeError('Process Runtime resolved CURRENT contains unexpected alarms')
    if any(
        alarm.get('evaluation', {}).get('status') != 'ACTIVE'
        or alarm.get('priority', {}).get('disposition') != 'PREDOMINANT'
        or PROCESS_TOOL
        not in {assignment['tool_key'] for assignment in alarm.get('assignments', [])}
        for alarm in alarms
    ):
        raise RuntimeError('Process Runtime did not activate and assign every alarm')
    return {
        'application': application,
        'distributed_count': distributed_count,
        'generic_count': ALARM_COUNT - distributed_count,
        'resolved_current': str(current_path),
        'resolved_alarm_count': len(alarms),
    }


# Exponer un comando de ejecución reproducible desde el workspace.
def main() -> None:
    parser = argparse.ArgumentParser(description='Isolated Process M2.1 Runtime qualification')
    parser.add_argument('--volume', type=Path, required=True)
    parser.add_argument('--application', required=True)
    parser.add_argument('--distributed', type=int, choices=(0, 1, 2), required=True)
    parser.add_argument('--execution-seconds', type=float, default=25.0)
    args = parser.parse_args()
    result = execute(
        volume=args.volume,
        application=args.application,
        distributed_count=args.distributed,
        seconds=args.execution_seconds,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
