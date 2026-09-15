from __future__ import annotations

# Este módulo modela el WORKSPACE genérico del Manager sin confundir su identidad local
# con la identidad durable de Source. El payload editable tiene una revisión propia y
# conserva además la revisión local que tenía al establecerse la BASE del trabajo.
# SourceSnapshot permanece como value object exacto: release, hash y token no se reducen
# a strings de revisión del Manager.

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus, ProjectionTarget
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


# Estado de presentación de la proyección respecto de Source.
class ManagerProjectionState(StrEnum):
    NO_SOURCE = 'no_source'
    NEVER_PROJECTED = 'never_projected'
    CURRENT = 'current'
    OUTDATED = 'outdated'


# WORKSPACE editable. revision identifica el contenido actual; base_payload_revision
# identifica el contenido local observado al establecer la BASE. Ninguna de las dos
# revisiones representa una SourceReleaseId.
@dataclass(frozen=True, slots=True)
class ManagerWorkspace:
    owner_subject_id: str
    revision: str
    base_payload_revision: str
    saved_at_utc: datetime
    payload: dict[str, object]
    base: SourceSnapshot

    def __post_init__(self) -> None:
        owner = self.owner_subject_id.strip()
        if not owner:
            raise ValueError('Manager workspace owner must not be empty')
        expected_revision = _build_workspace_revision(self.payload)
        if self.revision.strip() != expected_revision:
            raise ValueError('Manager workspace revision does not match payload')
        base_payload_revision = self.base_payload_revision.strip()
        if not base_payload_revision:
            raise ValueError('Manager workspace base payload revision must not be empty')
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise ValueError('Manager workspace timestamp must be timezone-aware')
        object.__setattr__(self, 'owner_subject_id', owner)
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'base_payload_revision', base_payload_revision)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))
        object.__setattr__(self, 'payload', deepcopy(self.payload))

    # Un workspace recién establecido parte sin cambios locales: ambas revisiones
    # de payload nacen iguales aunque Source tenga o no una release publicada.
    @classmethod
    def create(
        cls,
        *,
        owner_subject_id: str,
        payload: dict[str, object],
        base: SourceSnapshot,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        revision = _build_workspace_revision(payload)
        return cls(
            owner_subject_id=owner_subject_id,
            revision=revision,
            base_payload_revision=revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=payload,
            base=base,
        )

    # La suciedad funcional se decide únicamente comparando identidades locales.
    @property
    def has_local_changes(self) -> bool:
        return self.revision != self.base_payload_revision

    # Una edición cambia revision pero conserva tanto la BASE Source exacta como la
    # revisión local del payload base.
    def with_payload(
        self,
        payload: dict[str, object],
        *,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        return ManagerWorkspace(
            owner_subject_id=self.owner_subject_id,
            revision=_build_workspace_revision(payload),
            base_payload_revision=self.base_payload_revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=payload,
            base=self.base,
        )

    # Tras una publicación confirmada, rebase convierte el payload actual en la nueva
    # línea base local y adopta el SourceSnapshot publicado sin alterar el contenido.
    def rebase(
        self,
        base: SourceSnapshot,
        *,
        saved_at_utc: datetime | None = None,
    ) -> ManagerWorkspace:
        return ManagerWorkspace(
            owner_subject_id=self.owner_subject_id,
            revision=self.revision,
            base_payload_revision=self.revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
            payload=self.payload,
            base=base,
        )

    # El schema 2 persiste explícitamente base_payload_revision; el shape anterior no
    # puede expresar esta distinción y por eso no se interpreta silenciosamente.
    def to_document(self) -> dict[str, object]:
        return {
            'schema_version': 2,
            'owner_subject_id': self.owner_subject_id,
            'revision': self.revision,
            'base_payload_revision': self.base_payload_revision,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'payload': deepcopy(self.payload),
            'base': _source_snapshot_to_document(self.base),
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> ManagerWorkspace:
        try:
            payload = document['payload']
            base_document = document['base']
            if document.get('schema_version') != 2:
                raise TypeError
            if not isinstance(payload, dict) or not isinstance(base_document, dict):
                raise TypeError
            return cls(
                owner_subject_id=str(document['owner_subject_id']),
                revision=str(document['revision']),
                base_payload_revision=str(document['base_payload_revision']),
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
                payload=deepcopy(payload),
                base=_source_snapshot_from_document(base_document),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Manager workspace document is invalid') from error


# Verificación exacta: el conflicto funcional depende de identidad de release, no del
# token. Un token puede refrescarse manteniendo la misma release y seguir siendo publicable.
@dataclass(frozen=True, slots=True)
class ManagerSourceVerification:
    workspace_revision: str
    base: SourceSnapshot
    source: SourceSnapshot
    checked_at_utc: datetime

    def __post_init__(self) -> None:
        workspace_revision = self.workspace_revision.strip()
        if not workspace_revision:
            raise ValueError('Manager source verification workspace revision must not be empty')
        if self.base.source_key != self.source.source_key:
            raise ValueError('Manager source verification snapshots must use the same source key')
        if self.checked_at_utc.tzinfo is None or self.checked_at_utc.utcoffset() is None:
            raise ValueError('Manager source verification timestamp must be timezone-aware')
        object.__setattr__(self, 'workspace_revision', workspace_revision)
        object.__setattr__(self, 'checked_at_utc', self.checked_at_utc.astimezone(UTC))

    @property
    def matches(self) -> bool:
        return _release_id(self.base) == _release_id(self.source)

    @property
    def publishable(self) -> bool:
        return self.matches

    @property
    def conflict(self) -> bool:
        return not self.matches


# Contexto derivado para publicar: conserva basis_release de la BASE y usa el token
# fresco de SOURCE como precondición CAS.
@dataclass(frozen=True, slots=True)
class ManagerPublicationContext:
    workspace_revision: str
    source_key: SourceKey
    basis_release: SourceReleaseRef | None
    expected_concurrency_token: ConcurrencyToken | None

    def matches_payload(self, payload: dict[str, object]) -> bool:
        return _build_workspace_revision(payload) == self.workspace_revision


def verify_workspace_source(
    workspace: ManagerWorkspace,
    source: SourceSnapshot,
    *,
    checked_at_utc: datetime | None = None,
) -> ManagerSourceVerification:
    return ManagerSourceVerification(
        workspace_revision=workspace.revision,
        base=workspace.base,
        source=source,
        checked_at_utc=(checked_at_utc or datetime.now(UTC)).astimezone(UTC),
    )


def prepare_publication(verification: ManagerSourceVerification) -> ManagerPublicationContext:
    if not verification.matches:
        raise ValueError('Manager source changed while the workspace was being edited')
    return _publication_context(verification)


def prepare_conflict_overwrite(
    verification: ManagerSourceVerification,
) -> ManagerPublicationContext:
    if not verification.conflict:
        raise ValueError('Manager conflict overwrite requires a source conflict')
    return _publication_context(verification)


def select_projection_target(source: SourceSnapshot) -> ProjectionTarget:
    if source.current is None:
        raise ValueError('Cannot select a projection target without a published source release')
    return ProjectionTarget(
        source_key=source.source_key,
        source_release=source.current.release_ref,
    )


def resolve_manager_projection_state(status: ProjectionStatus) -> ManagerProjectionState:
    if status.source_current_release is None:
        return ManagerProjectionState.NO_SOURCE
    if status.alignment is ProjectionAlignment.NEVER_PROJECTED:
        return ManagerProjectionState.NEVER_PROJECTED
    if status.alignment is ProjectionAlignment.CURRENT:
        return ManagerProjectionState.CURRENT
    if status.alignment is ProjectionAlignment.OUTDATED:
        return ManagerProjectionState.OUTDATED
    raise ValueError('Unsupported projection alignment')


# La revisión local es SHA-256 del JSON canónico del payload y no una identidad Source.
def _build_workspace_revision(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _publication_context(
    verification: ManagerSourceVerification,
) -> ManagerPublicationContext:
    basis_release = None
    if verification.base.current is not None:
        basis_release = verification.base.current.release_ref
    return ManagerPublicationContext(
        workspace_revision=verification.workspace_revision,
        source_key=verification.source.source_key,
        basis_release=basis_release,
        expected_concurrency_token=verification.source.concurrency_token,
    )


def _release_id(snapshot: SourceSnapshot) -> SourceReleaseId | None:
    if snapshot.current is None:
        return None
    return snapshot.current.release_ref.release_id


def _source_snapshot_to_document(snapshot: SourceSnapshot) -> dict[str, object]:
    current = None
    if snapshot.current is not None:
        current = {
            'release_id': snapshot.current.release_ref.release_id.value,
            'published_at_utc': snapshot.current.release_ref.published_at_utc.isoformat(),
            'content_hash': {
                'algorithm': snapshot.current.content_hash.algorithm,
                'value': snapshot.current.content_hash.value,
            },
        }
    return {
        'source_key': snapshot.source_key.value,
        'current': current,
        'concurrency_token': (
            snapshot.concurrency_token.value if snapshot.concurrency_token is not None else None
        ),
    }


def _source_snapshot_from_document(document: dict[str, object]) -> SourceSnapshot:
    current_document = document.get('current')
    current = None
    if current_document is not None:
        if not isinstance(current_document, dict):
            raise TypeError
        content_hash_document = current_document['content_hash']
        if not isinstance(content_hash_document, dict):
            raise TypeError
        current = SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(str(current_document['release_id'])),
                published_at_utc=datetime.fromisoformat(str(current_document['published_at_utc'])),
            ),
            content_hash=Digest(
                algorithm=str(content_hash_document['algorithm']),
                value=str(content_hash_document['value']),
            ),
        )
    token_value = document.get('concurrency_token')
    token = ConcurrencyToken(str(token_value)) if token_value is not None else None
    return SourceSnapshot(
        source_key=SourceKey(str(document['source_key'])),
        current=current,
        concurrency_token=token,
    )
