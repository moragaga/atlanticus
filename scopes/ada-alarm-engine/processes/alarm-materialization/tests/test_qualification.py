from datetime import UTC, datetime

import pytest

from ada.alarms.materialization import (
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
)
from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmConfiguration,
    AlarmConfigurationProjection,
    AlarmConfigurationSnapshot,
)
from ada.contracts.tools import ToolDependencyManifest
from ada.processes.alarm_materialization import (
    AlarmMaterializationCandidate,
    AlarmMaterializationQualificationError,
    AlarmQualificationEvidence,
)


def _candidate() -> AlarmMaterializationCandidate:
    projection = AlarmConfigurationProjection(
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        source_release_id='alarm-r7',
        source_published_at_utc=datetime(2026, 10, 7, 12, tzinfo=UTC),
        projected_at_utc=datetime(2026, 10, 7, 12, 1, tzinfo=UTC),
        snapshot=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r9',
                tools=(),
            ),
        ),
    )
    return AlarmMaterializationCandidate.capture(projection)


def _evidence() -> AlarmQualificationEvidence:
    return AlarmQualificationEvidence(
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        source_release_id='alarm-r7',
        source_published_at_utc='2026-10-07T12:00:00+00:00',
        confirmed_tool_catalog_revision='tools-r9',
        qualified_at_utc='2026-10-07T12:02:00+00:00',
        producer='qualification-test',
        evidence_ref='evidence://alarm-r7',
        tools=ToolReconciliationQualification(green_tool_keys=()),
        evaluators=EvaluatorQualificationCatalog(
            qualified_keys=(EvaluatorQualificationKey('family_a', 'threshold'),),
        ),
    )


def test_qualification_round_trips_and_builds_materialization_provenance() -> None:
    candidate = _candidate()
    evidence = _evidence()

    restored = AlarmQualificationEvidence.from_document(evidence.to_document())
    provenance = restored.provenance(candidate)

    assert restored == evidence
    assert provenance.source_release_id == candidate.source_release_id
    assert provenance.confirmed_tool_catalog_revision == candidate.confirmed_tool_catalog_revision
    assert provenance.projection_digest == candidate.fingerprint
    assert provenance.qualification_digest == evidence.digest


def test_qualification_rejects_candidate_mismatch() -> None:
    document = _evidence().to_document()
    document['source_release_id'] = 'alarm-other'
    evidence = AlarmQualificationEvidence.from_document(document)

    with pytest.raises(AlarmMaterializationQualificationError):
        evidence.validate_candidate(_candidate())


def test_qualification_rejects_green_tool_outside_pinned_manifest() -> None:
    document = _evidence().to_document()
    document['green_tool_keys'] = ['tool_a']
    evidence = AlarmQualificationEvidence.from_document(document)

    with pytest.raises(AlarmMaterializationQualificationError):
        evidence.validate_candidate(_candidate())
