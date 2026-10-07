from dataclasses import replace

import pytest

from ada.alarms.core import AlarmResolutionKey
from ada.alarms.materialization import (
    AlarmMaterializationArtifact,
    AlarmMaterializationManifest,
    AlarmMaterializationProvenance,
    AlarmMaterializationReadyPointer,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
    materialization_result_id,
)


def provenance() -> AlarmMaterializationProvenance:
    return AlarmMaterializationProvenance(
        source_release_id='ALARMS-7',
        source_published_at_utc='2026-10-07T10:00:00+00:00',
        confirmed_tool_catalog_revision='TOOLS-4',
        projection_digest='a' * 64,
        qualification_digest='b' * 64,
        qualification_producer='manual-qualification',
        qualification_evidence_ref='qualification-7',
        qualified_at_utc='2026-10-07T10:05:00+00:00',
    )


def resolution_key() -> AlarmResolutionKey:
    return AlarmResolutionKey('ALARMS-7', 'TOOLS-4')


def artifact(label: str) -> AlarmMaterializationArtifact:
    return AlarmMaterializationArtifact(
        path=f'{label}.json',
        size_bytes=100,
        sha256='c' * 64,
    )


def test_ready_manifest_requires_exact_three_artifacts_and_round_trips() -> None:
    metadata = provenance()
    result_id = materialization_result_id(
        source_key='alarm_configuration',
        projection_digest=metadata.projection_digest,
        qualification_digest=metadata.qualification_digest,
    )
    manifest = AlarmMaterializationManifest(
        source_key='alarm_configuration',
        result_id=result_id,
        status=AlarmResolutionStatus.READY,
        resolution_key=resolution_key(),
        provenance=metadata,
        findings=(),
        artifacts={
            'engine': artifact('engine'),
            'modeler': artifact('modeler'),
            'delivery': artifact('delivery'),
        },
    )
    assert AlarmMaterializationManifest.from_document(manifest.to_document()) == manifest
    with pytest.raises(ValueError, match='requires Engine, Modeler, and Delivery'):
        replace(manifest, artifacts={'engine': artifact('engine')})


def test_blocked_manifest_requires_blocking_finding_and_no_artifacts() -> None:
    metadata = provenance()
    result_id = materialization_result_id(
        source_key='alarm_configuration',
        projection_digest=metadata.projection_digest,
        qualification_digest=metadata.qualification_digest,
    )
    finding = AlarmResolutionFinding(
        code='missing_tool',
        severity=AlarmResolutionFindingSeverity.BLOCKING,
        message='Tool is missing',
    )
    manifest = AlarmMaterializationManifest(
        source_key='alarm_configuration',
        result_id=result_id,
        status=AlarmResolutionStatus.BLOCKED,
        resolution_key=resolution_key(),
        provenance=metadata,
        findings=(finding,),
        artifacts={},
    )
    assert AlarmMaterializationManifest.from_document(manifest.to_document()) == manifest
    with pytest.raises(ValueError, match='must not contain artifacts'):
        replace(manifest, artifacts={'engine': artifact('engine')})


def test_ready_pointer_round_trips_exact_resolution_and_manifest_digest() -> None:
    metadata = provenance()
    pointer = AlarmMaterializationReadyPointer(
        source_key='alarm_configuration',
        result_id=materialization_result_id(
            source_key='alarm_configuration',
            projection_digest=metadata.projection_digest,
            qualification_digest=metadata.qualification_digest,
        ),
        resolution_key=resolution_key(),
        manifest_sha256='d' * 64,
    )
    assert AlarmMaterializationReadyPointer.from_document(pointer.to_document()) == pointer


def test_provenance_rejects_qualification_before_source_publication() -> None:
    with pytest.raises(ValueError, match='must not predate'):
        replace(provenance(), qualified_at_utc='2026-10-07T09:59:59+00:00')
