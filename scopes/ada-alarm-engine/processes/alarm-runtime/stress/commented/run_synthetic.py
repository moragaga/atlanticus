from __future__ import annotations

import argparse
import hashlib
import json
import math
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ada.alarms.core import AlarmEvaluation, AlarmStatus, EvidenceSnapshot
from ada.alarms.materialization import engine_from_document
from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.processes.alarm_runtime.bootstrap import load_configuration
from ada.processes.alarm_runtime.composition import build_composition
from ada.processes.alarm_runtime.session import (
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)

# Harness independiente: no altera el registro de evaluadores productivos.
from stress.recovery_verification import verify_recovery

SOURCE_KEY = 'alarm-configuration'
DEFAULT_APPLICATION = 'ada-alarm-engine-stress'
DEFAULT_SEED = 20261008
RANDOM_PHASE_SECONDS = 210
HOLD_PHASE_SECONDS = 335
FIXTURE_FILES = ('ready.json', 'manifest.json', 'engine.json', 'modeler.json', 'delivery.json')


# Secuencia reproducible por segundo, semilla y alarma.
def synthetic_decision(
    *, seed: int, tick: int, family_key: str, alarm_key: str
) -> bool:
    material = f'{seed}:{tick}:{family_key}:{alarm_key}'.encode('utf-8')
    return bool(hashlib.sha256(material).digest()[0] & 1)


# Fase con ACTIVE sostenido para generar evidencia cada 300 segundos.
def synthetic_phase(tick: int, *, random_seconds: int, hold_seconds: int) -> str:
    if tick < random_seconds:
        return 'RANDOM_INITIAL'
    if tick < random_seconds + hold_seconds:
        return 'HOLD_ACTIVE'
    return 'RANDOM_FINAL'


def make_evaluator(*, seed: int, started_at_utc: datetime, random_seconds: int, hold_seconds: int):
    def evaluate(context):
        tick = max(0, int((context.now - started_at_utc).total_seconds()))
        phase = synthetic_phase(tick, random_seconds=random_seconds, hold_seconds=hold_seconds)
        active = phase == 'HOLD_ACTIVE' or synthetic_decision(
            seed=seed,
            tick=tick,
            family_key=context.alarm_identity.family_key,
            alarm_key=context.alarm_identity.alarm_key,
        )
        return AlarmEvaluation(
            alarm_identity=context.alarm_identity,
            status=AlarmStatus.ACTIVE if active else AlarmStatus.INACTIVE,
            evaluated_at=context.now,
            evidence_snapshot=EvidenceSnapshot(
                contract_key='synthetic-alarm-stress',
                contract_version='1',
                payload={
                    'synthetic': True,
                    'phase': phase,
                    'seed': seed,
                    'tick': tick,
                    'reading': 100.0 if active else 0.0,
                    'threshold': 50.0,
                    'condition_active': active,
                },
            ),
        )
    return evaluate


def build_registry(*, engine, seed: int, started_at_utc: datetime, random_seconds: int, hold_seconds: int):
    evaluator = make_evaluator(
        seed=seed,
        started_at_utc=started_at_utc,
        random_seconds=random_seconds,
        hold_seconds=hold_seconds,
    )
    return AlarmEvaluatorRegistry(
        contracts=tuple(
            AlarmEvaluatorContract(
                family_key=planned.identity.family_key,
                evaluator_key=planned.evaluator_key,
                evaluator=evaluator,
                inputs=(),
            )
            for planned in engine.planned_alarms
        ),
    )


# Validación estricta de contratos, revisiones y hashes de materialización.
def validate_fixtures(fixture_root: Path) -> tuple[dict, dict]:
    data = {name: (fixture_root / name).read_bytes() for name in FIXTURE_FILES}
    docs = {name: json.loads(payload) for name, payload in data.items()}
    manifest = docs['manifest.json']
    ready = docs['ready.json']
    if manifest.get('status') != 'READY' or manifest.get('source_key') != SOURCE_KEY:
        raise ValueError('Fixture materialization must be READY for alarm-configuration')
    manifest_sha = hashlib.sha256(data['manifest.json']).hexdigest()
    if manifest_sha != ready.get('manifest_sha256'):
        raise ValueError('READY pointer manifest digest mismatch')
    if manifest.get('result_id') != ready.get('result_id'):
        raise ValueError('READY pointer result_id mismatch')
    for name in ('engine', 'modeler', 'delivery'):
        artifact = manifest['artifacts'][name]
        blob = data[name + '.json']
        if artifact['path'] != name + '.json':
            raise ValueError('Materialization artifact path mismatch')
        if len(blob) != artifact['size_bytes']:
            raise ValueError('Materialization artifact size mismatch')
        if hashlib.sha256(blob).hexdigest() != artifact['sha256']:
            raise ValueError('Materialization artifact digest mismatch')
    for name in FIXTURE_FILES:
        if docs[name].get('resolution_key') != ready['resolution_key']:
            raise ValueError(f'{name}: resolution_key mismatch')
    engine = engine_from_document(docs['engine.json'])
    plans = engine.planned_alarms
    if len(plans) != 3 or len({p.identity for p in plans}) != 3:
        raise ValueError('Stress fixture must contain exactly three distinct planned alarms')
    if len({(p.identity.family_key, p.evaluator_key) for p in plans}) != 3:
        raise ValueError('Stress fixture requires three distinct evaluator contracts')
    return ready, docs['engine.json']


# Instala únicamente los artefactos íntegros en un volumen aislado.
def install_fixtures(*, fixture_root: Path, application_root: Path, ready: dict) -> None:
    destination = materialization_root(application_root)
    version = destination / 'versions' / ready['result_id']
    version.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'engine.json', 'modeler.json', 'delivery.json'):
        (version / name).write_bytes((fixture_root / name).read_bytes())
    (destination / 'ready.json').write_bytes((fixture_root / 'ready.json').read_bytes())
    published = LocalAlarmMaterializationStore(root=destination).read_published_ready(
        source_key=SOURCE_KEY
    )
    if published.result_id != ready['result_id']:
        raise ValueError('Installed READY materialization could not be validated')


def directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob('*') if path.is_file() and not path.is_symlink()) if root.exists() else 0


def count_jsonl(path: Path):
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 3)


# Muestras periódicas de bytes sin leer payloads WAL/FACTS en plena escritura.
def sample_growth(*, application_root: Path, started_monotonic: float) -> dict:
    alarms = application_root / 'alarms'
    logs = application_root / 'logs'
    journal = alarms / 'runtime' / 'journal'
    facts = alarms / 'output' / 'facts'
    return {
        'elapsed_seconds': round(time.monotonic() - started_monotonic, 1),
        'journal_bytes': directory_size(journal),
        'facts_bytes': directory_size(facts),
        'current_bytes': directory_size(alarms / 'output' / 'current'),
        'logs_bytes': directory_size(logs),
        'facts_files': len(tuple(facts.rglob('*.jsonl'))) if facts.is_dir() else 0,
    }


def start_sampler(*, application_root: Path, interval_seconds: float):
    started = time.monotonic()
    stop = threading.Event()
    observations = [sample_growth(application_root=application_root, started_monotonic=started)]

    def sample_periodically():
        while not stop.wait(interval_seconds):
            observations.append(sample_growth(application_root=application_root, started_monotonic=started))

    worker = threading.Thread(target=sample_periodically, name='synthetic-stress-sampler', daemon=True)
    worker.start()
    return stop, worker, observations, started


# Informe al final con conteos y validación de recuperación durable.
def measure(*, application_root: Path, elapsed: float, outcome: str, seed: int, samples: list[dict]) -> dict:
    alarms = application_root / 'alarms'
    log_root = application_root / 'logs' / 'alarm-runtime'
    jsonls = tuple(sorted(log_root.glob('day=*/iterations.jsonl')))
    iterations = [entry for p in jsonls for entry in count_jsonl(p)]
    # Conteo íntegro en el cierre del Runtime, aunque se reduzcan los detalles por ciclo.
    executions = [
        entry
        for path in log_root.glob('day=*/executions.jsonl')
        for entry in count_jsonl(path)
        if entry.get('event') == 'execution.completed'
    ]
    total_iterations = sum(entry.get('iterations', 0) for entry in executions)
    if not executions:
        total_iterations = len(iterations)
    durations = [1000.0 * entry['duration_seconds'] for entry in iterations
                 if isinstance(entry.get('duration_seconds'), (int, float))]
    facts_paths = tuple(sorted((alarms / 'output' / 'facts').rglob('*.jsonl')))
    facts_rows = [record for path in facts_paths for record in count_jsonl(path)]
    counters = {
        key: 0 for key in ('occurrence_changes', 'episode_changes', 'evidence_records',
                           'technical_incident_changes', 'journey_events', 'management_effects')
    }
    for document in facts_rows:
        for key in counters:
            counters[key] += len(document.get('records', {}).get(key, []))
    wal_root = alarms / 'runtime' / 'journal'
    wal_paths = tuple(path for path in wal_root.rglob('*.jsonl') if path.is_file()) if wal_root.exists() else ()
    current_path = alarms / 'output' / 'current' / 'durable-latest.json'
    cursor_path = alarms / 'output' / 'state' / 'facts-export-cursor.json'
    diagnostic = verify_recovery(application_root=application_root)
    return {
        'test_type': 'synthetic-alarm-runtime-stress',
        'seed': seed,
        'result': outcome,
        'elapsed_seconds': round(elapsed, 3),
        'iteration_count': total_iterations,
        'iteration_summaries_logged': len(iterations),
        'durations_sample_basis': (
            'all' if len(iterations) == total_iterations else 'logged_subset'
        ),
        'evaluations_expected_from_logged_iterations': len(iterations) * 3,
        'evaluations_expected_from_runtime_iterations': max(0, total_iterations - 1) * 3,
        'durations_ms': {
            'p50': percentile(durations, 0.50),
            'p95': percentile(durations, 0.95),
            'max': round(max(durations), 3) if durations else None,
            'cycles_at_or_above_1s': sum(value >= 1000 for value in durations),
        },
        'journal_segment_count': len(wal_paths),
        'journal_bytes': sum(p.stat().st_size for p in wal_paths),
        'facts_batch_count': len(facts_rows),
        'facts_segment_count': len(facts_paths),
        'fact_record_counts': counters,
        'sizes_bytes': {
            'alarms_total': directory_size(alarms),
            'alarms_runtime': directory_size(alarms / 'runtime'),
            'alarms_output': directory_size(alarms / 'output'),
            'logs_total': directory_size(application_root / 'logs'),
            'iterations_jsonl': sum(p.stat().st_size for p in jsonls),
        },
        'current_exists': current_path.is_file(),
        'facts_cursor_exists': cursor_path.is_file(),
        'recovery_checks': diagnostic,
        'growth_samples': samples,
    }


# El programa niega ejecutar sobre un directorio con estado existente.
def main() -> None:
    parser = argparse.ArgumentParser(description='Isolated Alarm Runtime synthetic stress test')
    repo_root = Path(__file__).resolve().parents[5]
    parser.add_argument('--volume', type=Path, default=repo_root / '.runtime' / 'local-volume')
    parser.add_argument('--application', default=DEFAULT_APPLICATION)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--execution-seconds', type=float, default=600.0)
    parser.add_argument('--sample-seconds', type=float, default=30.0)
    parser.add_argument('--poll-seconds', type=float, default=1.0)
    parser.add_argument('--facts-segment-bytes', type=int, default=None)
    # 'all' conserva métricas completas del estrés; 'significant' verifica volumen reducido.
    parser.add_argument('--iteration-logs', choices=('all', 'significant'), default='all')
    parser.add_argument('--random-seconds', type=int, default=RANDOM_PHASE_SECONDS)
    parser.add_argument('--hold-seconds', type=int, default=HOLD_PHASE_SECONDS)
    args = parser.parse_args()
    if not args.application.startswith('ada-alarm-engine-stress') or '/' in args.application or '\\' in args.application:
        parser.error('application must use an isolated ada-alarm-engine-stress name')
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0:
        parser.error('poll-seconds must be positive')
    if not math.isfinite(args.execution_seconds) or args.execution_seconds <= 15:
        parser.error('execution-seconds must exceed 15 seconds')
    if not math.isfinite(args.sample_seconds) or args.sample_seconds <= 0:
        parser.error('sample-seconds must be positive')
    if args.facts_segment_bytes is not None and args.facts_segment_bytes < 512:
        parser.error('facts-segment-bytes must be at least 512')
    if args.random_seconds < 0 or args.hold_seconds < 301:
        parser.error('hold-seconds must be at least 301; random-seconds must be nonnegative')
    volume = args.volume.expanduser().resolve()
    fixture_root = Path(__file__).resolve().parent / 'fixtures'
    ready, engine_document = validate_fixtures(fixture_root)
    app_root = volume / args.application
    if app_root.is_symlink() or (app_root.exists() and any(app_root.iterdir())):
        parser.error(f'isolated application already contains data: {app_root}; choose a new --application')
    app_root.mkdir(parents=True, exist_ok=True)
    install_fixtures(fixture_root=fixture_root, application_root=app_root, ready=ready)
    started = datetime.now(UTC).replace(microsecond=0)
    registry = build_registry(
        engine=engine_from_document(engine_document),
        seed=args.seed,
        started_at_utc=started,
        random_seconds=args.random_seconds,
        hold_seconds=args.hold_seconds,
    )
    publication = LocalAlarmMaterializationStore(root=materialization_root(app_root))
    execution_session = build_alarm_execution_session(
        configuration=publication.read_published_engine(source_key=SOURCE_KEY),
        evaluator_registry=registry,
    )
    if execution_session.data_plan.views or any(entry.inputs for entry in execution_session.entries):
        raise ValueError('Synthetic stress must not request operational dataset inputs')
    config = {
        'ENVIRONMENT': 'local',
        'APPLICATION': args.application,
        'VOLUMEN_PATH': str(volume),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'synthetic-no-inputs',
        'ALARM_RUNTIME_POLL_SECONDS': str(args.poll_seconds),
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'false',
    }
    manifest = {
        'test_type': 'synthetic-alarm-runtime-stress',
        'seed': args.seed,
        'started_at_utc': started.isoformat(),
        'fixture_result_id': ready['result_id'],
        'application': args.application,
        'poll_seconds': args.poll_seconds,
        'facts_segment_bytes': args.facts_segment_bytes,
        'iteration_logs': args.iteration_logs,
        'execution_seconds': args.execution_seconds,
        'sample_seconds': args.sample_seconds,
        'random_seconds': args.random_seconds,
        'hold_seconds': args.hold_seconds,
        'planned_alarm_count': len(execution_session.entries),
        'operational_inputs': 0,
        'production_data_bypass': True,
    }
    (app_root / 'stress-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'STRESS ISOLATED | application={args.application} | seed={args.seed} | poll={args.poll_seconds}s', flush=True)
    outcome = 'failed'
    stop, worker, samples, clock_started = start_sampler(application_root=app_root, interval_seconds=args.sample_seconds)
    try:
        configuration = load_configuration(
            process_root=Path(__file__).resolve().parents[1], environ=config
        )
        composition = build_composition(configuration=configuration, evaluator_registry=registry)
        if args.facts_segment_bytes is not None:
            composition.publications.facts.max_segment_bytes = args.facts_segment_bytes
        composition.definition = replace(
            composition.definition,
            execution_timeout_seconds=args.execution_seconds,
            iteration_summary_every=1 if args.iteration_logs == 'all' else 0,
        )
        result = composition.execute(argv=())
        outcome = str(result.status)
    finally:
        stop.set()
        worker.join()
        samples.append(sample_growth(application_root=app_root, started_monotonic=clock_started))
        elapsed = (datetime.now(UTC) - started).total_seconds()
        report = measure(application_root=app_root, elapsed=elapsed, outcome=outcome, seed=args.seed, samples=samples)
        if report['recovery_checks']['status'] != 'verified':
            report['runtime_result'] = report['result']
            report['result'] = 'failed'
        destination = app_root / 'stress-report.json'
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'STRESS REPORT | {destination}', flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if outcome.lower().endswith('success') and report['recovery_checks']['status'] != 'verified':
            raise RuntimeError('Incremental recovery verification failed after stress execution')


if __name__ == '__main__':
    main()
