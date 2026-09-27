# Las qualifications son entradas explícitas externas, nunca GREEN inferido por el propio proceso.
# El provider de archivo habilita ejecución manual controlada; debe conectarse el productor operacional real.
# La evidencia se valida contra source release, publicación y Tool revision del candidato.
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ada_command_center.alarms.materialization import (
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
)
from ada_command_center.processes.alarms_materialization.candidate import (
    AlarmMaterializationCandidate,
)


# Contrato AlarmQualificationError: mantiene invariantes de esta frontera.
class AlarmQualificationError(RuntimeError):
    pass


# Operación _canonical: mantiene invariantes de esta frontera.
def _canonical(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
        'utf-8'
    )


# Operación _required_text: mantiene invariantes de esta frontera.
def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlarmQualificationError(
            f'{name} must be non-empty text without surrounding whitespace'
        )
    return value


@dataclass(frozen=True, slots=True)
# Contrato AlarmQualificationEvidence: mantiene invariantes de esta frontera.
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

    @classmethod
    def from_document(cls, document: object) -> AlarmQualificationEvidence:
        if not isinstance(document, dict) or document.get('schema_version') != 1:
            raise AlarmQualificationError('Alarm qualification document schema is invalid')
        try:
            greens = document['green_tool_keys']
            qualified = document['qualified_evaluators']
            if not isinstance(greens, list) or not isinstance(qualified, list):
                raise TypeError
            if any(not isinstance(item, dict) for item in qualified):
                raise TypeError
            published = _required_text(
                document['source_published_at_utc'], 'source_published_at_utc'
            )
            qualified_at = _required_text(document['qualified_at_utc'], 'qualified_at_utc')
            for name, value in (
                ('source_published_at_utc', published),
                ('qualified_at_utc', qualified_at),
            ):
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise AlarmQualificationError(f'{name} must be timezone-aware')
            return cls(
                source_key=_required_text(document['source_key'], 'source_key'),
                source_release_id=_required_text(
                    document['source_release_id'], 'source_release_id'
                ),
                source_published_at_utc=published,
                confirmed_tool_catalog_revision=_required_text(
                    document['confirmed_tool_catalog_revision'], 'confirmed_tool_catalog_revision'
                ),
                qualified_at_utc=qualified_at,
                producer=_required_text(document['producer'], 'producer'),
                evidence_ref=_required_text(document['evidence_ref'], 'evidence_ref'),
                tools=ToolReconciliationQualification(green_tool_keys=tuple(greens)),
                evaluators=EvaluatorQualificationCatalog(
                    qualified_keys=tuple(
                        EvaluatorQualificationKey(
                            family_key=item['family_key'], evaluator_key=item['evaluator_key']
                        )
                        for item in qualified
                    )
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmQualificationError(
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
                {'family_key': item.family_key, 'evaluator_key': item.evaluator_key}
                for item in self.evaluators.qualified_keys
            ],
        }

    @property
    def digest(self) -> str:
        return sha256(_canonical(self.to_document())).hexdigest()

    def validate_candidate(self, candidate: AlarmMaterializationCandidate) -> None:
        projection = candidate.projection
        if (
            self.source_key != candidate.source_key.value
            or self.source_release_id != candidate.alarm_configuration_revision
            or self.confirmed_tool_catalog_revision != candidate.confirmed_tool_catalog_revision
            or datetime.fromisoformat(self.source_published_at_utc)
            != projection.source_published_at_utc
        ):
            raise AlarmQualificationError('Alarm qualification evidence does not match candidate')
        if datetime.fromisoformat(self.qualified_at_utc) < projection.source_published_at_utc:
            raise AlarmQualificationError(
                'Alarm qualification evidence predates source publication'
            )


# Contrato AlarmQualificationProvider: mantiene invariantes de esta frontera.
class AlarmQualificationProvider(Protocol):
    def load(self, candidate: AlarmMaterializationCandidate) -> AlarmQualificationEvidence: ...


# Contrato JsonFileAlarmQualificationProvider: mantiene invariantes de esta frontera.
class JsonFileAlarmQualificationProvider:
    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError('Alarm qualification file path must be absolute')
        self._path = path

    def load(self, candidate: AlarmMaterializationCandidate) -> AlarmQualificationEvidence:
        try:
            document = json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as error:
            raise AlarmQualificationError('Could not load Alarm qualification evidence') from error
        evidence = AlarmQualificationEvidence.from_document(document)
        evidence.validate_candidate(candidate)
        return evidence
