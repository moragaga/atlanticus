from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ada.contracts.alarms.facts_segments import (
    FactsSegmentInventoryError,
    SealedFactsSegment,
    list_sealed_facts_segments,
    verify_sealed_facts_segment,
)

FIRST = 'facts/year=2026/month=10/day=09/hour=16/part-0000.jsonl'
SECOND = 'facts/year=2026/month=10/day=09/hour=16/part-0001.jsonl'
THIRD = 'facts/year=2026/month=10/day=09/hour=17/part-0000.jsonl'


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()


def _cursor(root, active):
    document = {
        'document_type': 'ada_command_center_engine_facts_export_cursor',
        'schema_version': 4,
        'artifact_ref': None,
        'journal_position': None,
        'segment_path': None,
        'record_start': None,
        'record_end': None,
        'record_sha256': None,
    }
    if active is not None:
        document.update(
            artifact_ref={'source_key': 'fixture'},
            journal_position={'segment_id': 'fixture', 'byte_offset': 3},
            segment_path=active,
            record_start=0,
            record_end=3,
            record_sha256='a' * 64,
        )
    document['cursor_sha256'] = _digest(document)
    target = root / 'state/facts-export-cursor.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding='utf-8')
    return target


def _segment(root, relative, value=b'row\n'):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def test_no_commits_means_no_sealed_segments(tmp_path):
    _cursor(tmp_path, None)
    assert list_sealed_facts_segments(root=tmp_path) == ()


def test_active_segment_is_never_sealed_even_after_hours(tmp_path):
    _segment(tmp_path, FIRST)
    _cursor(tmp_path, FIRST)
    assert list_sealed_facts_segments(root=tmp_path) == ()


def test_rotated_segments_are_listed_without_modifying_the_active_one(tmp_path):
    old = _segment(tmp_path, FIRST, b'first\n')
    _segment(tmp_path, SECOND, b'second\n')
    active = _segment(tmp_path, THIRD, b'current\n')
    _cursor(tmp_path, THIRD)
    discovered = list_sealed_facts_segments(root=tmp_path)
    assert [item.relative_path for item in discovered] == [FIRST, SECOND]
    assert discovered[0].size_bytes == 6
    assert discovered[0].mtime_ns == old.stat().st_mtime_ns
    assert active.read_bytes() == b'current\n'


def test_sealed_segment_verification_returns_exact_content_fingerprint(tmp_path):
    content = b'{"commit":"x"}\n'
    _segment(tmp_path, FIRST, content)
    _segment(tmp_path, SECOND)
    _cursor(tmp_path, SECOND)
    only = list_sealed_facts_segments(root=tmp_path)[0]
    verified = verify_sealed_facts_segment(root=tmp_path, segment=only)
    assert verified.relative_path == FIRST
    assert verified.size_bytes == len(content)
    assert verified.sha256 == hashlib.sha256(content).hexdigest()


def test_changed_sealed_file_after_inventory_is_rejected(tmp_path):
    file = _segment(tmp_path, FIRST, b'old\n')
    _segment(tmp_path, SECOND)
    _cursor(tmp_path, SECOND)
    discovered = list_sealed_facts_segments(root=tmp_path)[0]
    file.write_bytes(b'changed\n')
    with pytest.raises(FactsSegmentInventoryError, match='changed since inventory'):
        verify_sealed_facts_segment(root=tmp_path, segment=discovered)


def test_active_segment_cannot_be_verified_from_stale_inventory(tmp_path):
    _segment(tmp_path, FIRST)
    _cursor(tmp_path, FIRST)
    candidate = SealedFactsSegment(FIRST, 4, 0)
    with pytest.raises(FactsSegmentInventoryError, match='not sealed'):
        verify_sealed_facts_segment(root=tmp_path, segment=candidate)


def test_path_traversal_is_rejected(tmp_path):
    _segment(tmp_path, SECOND)
    _cursor(tmp_path, SECOND)
    candidate = SealedFactsSegment('../outside', 0, 0)
    with pytest.raises(FactsSegmentInventoryError, match='Invalid FACTS segment path'):
        verify_sealed_facts_segment(root=tmp_path, segment=candidate)


def test_symlinked_segment_is_rejected(tmp_path):
    target = tmp_path / 'outside.txt'
    target.write_bytes(b'outside')
    symlink = tmp_path / FIRST
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(target)
    _segment(tmp_path, SECOND)
    _cursor(tmp_path, SECOND)
    with pytest.raises(FactsSegmentInventoryError, match='not a regular local file'):
        list_sealed_facts_segments(root=tmp_path)


def test_non_v4_files_are_not_part_of_inventory(tmp_path):
    _segment(tmp_path, FIRST)
    _segment(tmp_path, SECOND)
    _segment(tmp_path, 'facts/year=2026/month=10/day=09/hour=16/random.jsonl')
    _cursor(tmp_path, SECOND)
    assert [x.relative_path for x in list_sealed_facts_segments(root=tmp_path)] == [FIRST]


def test_invalid_publisher_cursor_blocks_inventory(tmp_path):
    _segment(tmp_path, FIRST)
    path = _cursor(tmp_path, FIRST)
    data = json.loads(path.read_text())
    data['record_end'] = 900
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='cursor integrity'):
        list_sealed_facts_segments(root=tmp_path)


def test_root_must_be_absolute():
    with pytest.raises(ValueError, match='absolute Path'):
        list_sealed_facts_segments(root=Path('relative'))


def _facts_position(relative_path):
    from ada.contracts.alarms.facts_stream import FactsStreamPosition

    return FactsStreamPosition(
        segment_path=relative_path,
        record_start=0,
        record_end=4,
        record_sha256='0' * 64,
        artifact_ref={'source_key': 'fixture'},
    )


def test_retirement_requires_verified_backup_and_all_consumers(tmp_path):
    from ada.contracts.alarms.facts_segments import (
        ArchivedFactsReceipt,
        plan_facts_retirement_candidates,
    )

    _segment(tmp_path, FIRST, b'first\n')
    _segment(tmp_path, SECOND, b'second\n')
    _segment(tmp_path, THIRD, b'active\n')
    _cursor(tmp_path, THIRD)
    verified = tuple(
        verify_sealed_facts_segment(root=tmp_path, segment=item)
        for item in list_sealed_facts_segments(root=tmp_path)
    )
    backups = tuple(
        ArchivedFactsReceipt(
            relative_path=item.relative_path,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
            remote_ref='blob/archive/' + item.relative_path,
        )
        for item in verified
    )
    planner = plan_facts_retirement_candidates
    assert planner(
        verified_segments=verified,
        archive_receipts=backups,
        required_consumer_positions={},
    ) == ()
    assert planner(
        verified_segments=verified,
        archive_receipts=backups,
        required_consumer_positions={'historian': None},
    ) == ()
    assert planner(
        verified_segments=verified,
        archive_receipts=backups,
        required_consumer_positions={
            'historian': _facts_position(THIRD),
            'modeler': _facts_position(FIRST),
        },
    ) == ()
    assert planner(
        verified_segments=verified,
        archive_receipts=backups,
        required_consumer_positions={
            'historian': _facts_position(THIRD),
            'modeler': _facts_position(SECOND),
        },
    ) == (verified[0],)
    assert planner(
        verified_segments=verified,
        archive_receipts=backups,
        required_consumer_positions={
            'historian': _facts_position(THIRD),
            'modeler': _facts_position(THIRD),
        },
    ) == verified


def test_retirement_never_uses_missing_or_invalid_archive_proof(tmp_path):
    from ada.contracts.alarms.facts_segments import (
        ArchivedFactsReceipt,
        plan_facts_retirement_candidates,
    )

    _segment(tmp_path, FIRST, b'first\n')
    _segment(tmp_path, SECOND)
    _cursor(tmp_path, SECOND)
    verified = (
        verify_sealed_facts_segment(
            root=tmp_path, segment=list_sealed_facts_segments(root=tmp_path)[0]
        ),
    )
    invalid_backup = ArchivedFactsReceipt(
        relative_path=FIRST,
        size_bytes=verified[0].size_bytes,
        sha256='f' * 64,
        remote_ref='blob/archive/first',
    )
    assert plan_facts_retirement_candidates(
        verified_segments=verified,
        archive_receipts=(invalid_backup,),
        required_consumer_positions={'historian': _facts_position(SECOND)},
    ) == ()
    assert plan_facts_retirement_candidates(
        verified_segments=verified,
        archive_receipts=(),
        required_consumer_positions={'historian': _facts_position(SECOND)},
    ) == ()


def test_retirement_rejects_duplicate_backup_receipts(tmp_path):
    from ada.contracts.alarms.facts_segments import (
        ArchivedFactsReceipt,
        plan_facts_retirement_candidates,
    )

    proof = ArchivedFactsReceipt(FIRST, 4, 'a' * 64, 'blob/archive/first')
    with pytest.raises(ValueError, match='Duplicate FACTS archive receipt'):
        plan_facts_retirement_candidates(
            verified_segments=(),
            archive_receipts=(proof, proof),
            required_consumer_positions={'historian': _facts_position(SECOND)},
        )
