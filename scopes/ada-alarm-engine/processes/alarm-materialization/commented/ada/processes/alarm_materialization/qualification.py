# La qualification es evidencia controlada y específica del candidate; su digest participa en la identidad durable.
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ada.alarms.materialization import (
    AlarmMaterializationProvenance,
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
    canonical_json_bytes,
)
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import AlarmMaterializationQualificationError


# Evidencia inmutable que fija exactamente qué candidate, Tools y evaluators fueron calificados.
@dataclass(frozen=True, slots=True)
class AlarmQualificationEvidence:
    source_key: str
    source_release_id: str
    source_published_at_utc: str
    confirmed_tool_catalog_revision: str
    qualified_at_utc: str
    producer: str
    evidence_ref: str
    tools: ToolReconciliationQualification
    evaluators: EvaluatorQualificationCatalog

    def __post_init__(self) -> None:
        for field_name in (
            'source_key',
            'source_release_id',
            'source_published_at_utc',
            'confirmed_tool_catalog_revision',
            'qualified_at_utc',
            'producer',
            'evidence_ref',
        ):
            _require_text(getattr(self, field_name), field_name)
        _aware_datetime(self.source_published_at_utc, 'source_published_at_utc')
        _aware_datetime(self.qualified_at_utc, 'qualified_at_utc')
        if not isinstance(self.tools, ToolReconciliationQualification):
            raise TypeError('tools must be a ToolReconciliationQualification')
        if not isinstance(self.evaluators, EvaluatorQualificationCatalog):
            raise TypeError('evaluators must be an EvaluatorQualificationCatalog')

    @classmethod
    def from_document(cls, document: object) -> AlarmQualificationEvidence:
        required = {
            'schema_version',
            'source_key',
            'source_release_id',
            'source_published_at_utc',
            'confirmed_tool_catalog_revision',
            'qualified_at_utc',
            'producer',
            'evidence_ref',
            'green_tool_keys',
            'qualified_evaluators',
        }
        if not isinstance(document, dict) or set(document) != required:
            raise AlarmMaterializationQualificationError(
                'Alarm qualification document contract is invalid'
            )
        if document.get('schema_version') != 1:
            raise AlarmMaterializationQualificationError(
                'Alarm qualification document schema is invalid'
            )
        try:
            green_tool_keys = document['green_tool_keys']
            qualified_evaluators = document['qualified_evaluators']
            if not isinstance(green_tool_keys, list) or not isinstance(qualified_evaluators, list):
                raise TypeError
            if any(not isinstance(item, dict) for item in qualified_evaluators):
                raise TypeError
            return cls(
                source_key=_require_text(document['source_key'], 'source_key'),
                source_release_id=_require_text(document['source_release_id'], 'source_release_id'),
                source_published_at_utc=_require_text(
                    document['source_published_at_utc'], 'source_published_at_utc'
                ),
                confirmed_tool_catalog_revision=_require_text(
                    document['confirmed_tool_catalog_revision'],
                    'confirmed_tool_catalog_revision',
                ),
                qualified_at_utc=_require_text(document['qualified_at_utc'], 'qualified_at_utc'),
                producer=_require_text(document['producer'], 'producer'),
                evidence_ref=_require_text(document['evidence_ref'], 'evidence_ref'),
                tools=ToolReconciliationQualification(green_tool_keys=tuple(green_tool_keys)),
                evaluators=EvaluatorQualificationCatalog(
                    qualified_keys=tuple(
                        EvaluatorQualificationKey(
                            family_key=item['family_key'],
                            evaluator_key=item['evaluator_key'],
                        )
                        for item in qualified_evaluators
                    )
                ),
            )
        except AlarmMaterializationQualificationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmMaterializationQualificationError(
                'Alarm qualification document contract is invalid'
            ) from error

    def to_document(self) -> dict[str, object]:
        return {
            'schema_version': 1,
            'source_key': self.source_key,
            'source_release_id': self.source_release_id,
            'source_published_at_utc': self.source_published_at_utc,
            'confirmed_tool_catalog_revision': self.confirmed_tool_catalog_revision,
            'qualified_at_utc': self.qualified_at_utc,
            'producer': self.producer,
            'evidence_ref': self.evidence_ref,
            'green_tool_keys': list(self.tools.green_tool_keys),
            'qualified_evaluators': [
                {'family_key': key.family_key, 'evaluator_key': key.evaluator_key}
                for key in self.evaluators.qualified_keys
            ],
        }

    @property
    def digest(self) -> str:
        return sha256(canonical_json_bytes(self.to_document())).hexdigest()

    def validate_candidate(self, candidate: AlarmMaterializationCandidate) -> None:
        if not isinstance(candidate, AlarmMaterializationCandidate):
            raise TypeError('candidate must be an AlarmMaterializationCandidate')
        projection = candidate.projection
        if (
            self.source_key != candidate.source_key
            or self.source_release_id != candidate.source_release_id
            or self.confirmed_tool_catalog_revision != candidate.confirmed_tool_catalog_revision
            or _aware_datetime(self.source_published_at_utc, 'source_published_at_utc')
            != projection.source_published_at_utc
        ):
            raise AlarmMaterializationQualificationError(
                'Alarm qualification evidence does not match candidate'
            )
        if (
            _aware_datetime(self.qualified_at_utc, 'qualified_at_utc')
            < projection.source_published_at_utc
        ):
            raise AlarmMaterializationQualificationError(
                'Alarm qualification evidence predates source publication'
            )
        available_tool_keys = {tool.tool_key for tool in projection.snapshot.tool_dependencies.tools}
        unknown_green = set(self.tools.green_tool_keys).difference(available_tool_keys)
        if unknown_green:
            raise AlarmMaterializationQualificationError(
                'Alarm qualification evidence references Tools outside the pinned manifest'
            )

    def provenance(self, candidate: AlarmMaterializationCandidate) -> AlarmMaterializationProvenance:
        self.validate_candidate(candidate)
        return AlarmMaterializationProvenance(
            source_release_id=self.source_release_id,
            source_published_at_utc=self.source_published_at_utc,
            confirmed_tool_catalog_revision=self.confirmed_tool_catalog_revision,
            projection_digest=candidate.fingerprint,
            qualification_digest=self.digest,
            qualification_producer=self.producer,
            qualification_evidence_ref=self.evidence_ref,
            qualified_at_utc=self.qualified_at_utc,
        )


class AlarmQualificationProvider(Protocol):
    def load(self, candidate: AlarmMaterializationCandidate) -> AlarmQualificationEvidence: ...


# El provider relee el archivo en cada uso para que una modificación concurrente cambie el digest y aborte la publicación.
class JsonFileAlarmQualificationProvider:
    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError('Alarm qualification file path must be an absolute Path')
        self._path = path

    def load(self, candidate: AlarmMaterializationCandidate) -> AlarmQualificationEvidence:
        try:
            document = json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as error:
            raise AlarmMaterializationQualificationError(
                'Could not load Alarm qualification evidence'
            ) from error
        evidence = AlarmQualificationEvidence.from_document(document)
        evidence.validate_candidate(candidate)
        return evidence


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlarmMaterializationQualificationError(
            f'{name} must be non-empty text without surrounding whitespace'
        )
    return value


def _aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise AlarmMaterializationQualificationError(f'{name} must be an ISO datetime')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise AlarmMaterializationQualificationError(f'{name} must be an ISO datetime') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlarmMaterializationQualificationError(f'{name} must be timezone-aware')
    return parsed
