# Espejo pedagógico de la verificación incremental del estrés.
# Valida sobre copia temporal, sin escribir en el volumen fuente.
from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from uuid import uuid4

from ada.alarms.persistence.operational import EngineCommitRecord, GroupRuntimeSnapshot
from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence


# Valida recovery, invariantes y continuidad de commit tras la compactación.
def verify_recovery(*, application_root: Path) -> dict:
    diagnostic = {
        'mode': 'incremental-checkpoint',
        'status': 'failed',
        'effective_head_valid': False,
        'head_aligned': False,
        'snapshots_preserved': False,
        'retained_wal_commit_count': None,
        'continuation_committed': False,
        'continuation_recovered': False,
        'durable_position': None,
        'continuation_position': None,
        'error': None,
    }
    try:
        source = Path(application_root)
        if not source.is_dir():
            raise ValueError('Stress application volume does not exist')
        # Se aísla físicamente el volumen antes de recuperar o escribir.
        with TemporaryDirectory(prefix='alarm-stress-recovery-') as directory:
            root = copytree(source, Path(directory) / 'application')
            store = IncrementalAlarmPersistence(application_root=root)
            original_head = store.read_head()
            original_snapshots = tuple(snapshot.as_document() for snapshot in store.list_snapshots())
            if not original_head.aligned or original_head.durable is None:
                raise AssertionError('Stress WAL head is not aligned and durable')
            effective_path = root / 'alarms/runtime/state/effective-head.json'
            if not effective_path.is_file():
                raise AssertionError('Stress EFFECTIVE head is missing')
            original_effective = json.loads(effective_path.read_text(encoding='utf-8'))
            # La recuperación debe preservar HEAD, snapshots y EFFECTIVE.
            recovered = store.recover(
                assert_authority=_assert_authority,
                fenced_mutation=nullcontext,
            )
            if recovered.durable != original_head.durable or store.read_head() != original_head:
                raise AssertionError('Incremental recovery changed the durable head')
            if tuple(snapshot.as_document() for snapshot in store.list_snapshots()) != original_snapshots:
                raise AssertionError('Incremental recovery changed committed snapshots')
            effective = store.read_effective_head()
            if effective is None or effective.as_document() != original_effective:
                raise AssertionError('Incremental recovery changed EFFECTIVE')
            diagnostic['head_aligned'] = True
            diagnostic['effective_head_valid'] = True
            diagnostic['snapshots_preserved'] = True
            diagnostic['durable_position'] = original_head.durable.as_document()
            retained = store.read_durable_records()
            diagnostic['retained_wal_commit_count'] = len(retained)
            if not retained:
                raise AssertionError('No retained durable EngineCommitRecord for continuation')
            last_record = retained[-1].record
            if not isinstance(last_record, EngineCommitRecord):
                raise AssertionError('Retained WAL contains no usable group commit')
            if not last_record.commit.affected_alarms:
                raise AssertionError('Retained group commit has no affected alarms')
            snapshot = store.read_snapshot(last_record.commit.priority_group)
            if snapshot is None:
                raise AssertionError('Committed group snapshot is missing')
            token = uuid4().hex
            new_id = f'stress-continuation-{token}'
            last_time = datetime.fromisoformat(last_record.commit.evaluated_at.replace('Z', '+00:00'))
            evaluated_at = max(datetime.now(UTC), last_time + timedelta(microseconds=1))
            new_snapshot = snapshot.as_document()
            new_snapshot['last_commit_id'] = new_id
            for alarm in new_snapshot['alarms'].values():
                alarm['last_commit_id'] = new_id
            # Se agrega un commit ordinario sin modificar el ciclo vital de las alarmas.
            continuation = EngineCommitRecord.create(
                commit=replace(
                    last_record.commit,
                    commit_id=new_id,
                    previous_commit_id=snapshot.last_commit_id,
                    cycle_id=f'stress-continuation-cycle-{token}',
                    evaluated_at=evaluated_at.isoformat(),
                    committed_at=evaluated_at.isoformat(),
                ),
                snapshot_after=GroupRuntimeSnapshot(new_snapshot),
                records={},
            )
            committed = store.commit_batch(
                (continuation,),
                assert_authority=_assert_authority,
                fenced_mutation=nullcontext,
            )
            if committed.durable == original_head.durable or committed.materialized != committed.durable:
                raise AssertionError('Continuation did not advance the aligned durable head')
            diagnostic['continuation_committed'] = True
            diagnostic['continuation_position'] = committed.durable.as_document()
            # El segundo proceso verifica que el nuevo commit ya es recuperable.
            restarted = IncrementalAlarmPersistence(application_root=root)
            continued = restarted.recover(
                assert_authority=_assert_authority,
                fenced_mutation=nullcontext,
            )
            if continued.durable != committed.durable or restarted.read_head().durable != committed.durable:
                raise AssertionError('Continuation was not recovered durably')
            if restarted.read_snapshot(snapshot.priority_group) != continuation.snapshot_after:
                raise AssertionError('Continuation snapshot did not survive recovery')
            restarted_effective = restarted.read_effective_head()
            if restarted_effective is None or restarted_effective.as_document() != original_effective:
                raise AssertionError('Continuation changed EFFECTIVE')
            diagnostic['continuation_recovered'] = True
            diagnostic['status'] = 'verified'
    except Exception as error:
        diagnostic['error'] = f'{type(error).__name__}: {error}'
    return diagnostic


def _assert_authority() -> None:
    return None


# Permite validar volúmenes archivados sin repetir todo el estrés.
def main() -> int:
    parser = argparse.ArgumentParser(description='Verify incremental Alarm Engine recovery on a temporary copy')
    parser.add_argument('--application-root', type=Path, required=True)
    args = parser.parse_args()
    result = verify_recovery(application_root=args.application_root.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
