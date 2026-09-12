from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Generic, Protocol, TypeVar

from atlanticus.web.projection.errors import ProjectionExecutionError, ProjectionInvariantError
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionExecutionResult,
    ProjectionRecord,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore

PayloadT = TypeVar('PayloadT')
ProjectionClock = Callable[[], datetime]


# El builder contiene la transformación propia del dominio y recibe siempre una release Source exacta.
class ProjectionBuilder(Protocol[PayloadT]):
    def build(
        self,
        *,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> PayloadT: ...


# El servicio separa observación de current de la ejecución exact-release.
class SourceProjectionService(Generic[PayloadT]):
    def __init__(
        self,
        *,
        source: SourceStore,
        projection: ProjectionStore[PayloadT],
        builder: ProjectionBuilder[PayloadT],
        clock: ProjectionClock | None = None,
    ) -> None:
        self._source = source
        self._projection = projection
        self._builder = builder
        self._clock = clock or _utc_now

    # Esta operación observa current sólo para construir un target inmutable que el caller puede conservar.
    def select_current_target(self, source_key: SourceKey) -> ProjectionTarget | None:
        snapshot = self._source.get_current(source_key)
        if snapshot.current is None:
            return None
        return ProjectionTarget(
            source_key=source_key,
            source_release=snapshot.current.release_ref,
        )

    # Status compara identidades de release, nunca content_hash.
    def get_status(self, source_key: SourceKey) -> ProjectionStatus:
        snapshot = self._source.get_current(source_key)
        active = self._projection.get_active(source_key)
        current_release = snapshot.current.release_ref if snapshot.current is not None else None
        if active is None:
            return ProjectionStatus(
                alignment=ProjectionAlignment.NEVER_PROJECTED,
                source_current_release=current_release,
                projected_source_release=None,
            )
        if active.source_key != source_key:
            raise ProjectionInvariantError('Projection store returned a different source key')
        projected_release = active.source_release
        alignment = (
            ProjectionAlignment.CURRENT
            if current_release is not None
            and projected_release.release_id == current_release.release_id
            else ProjectionAlignment.OUTDATED
        )
        return ProjectionStatus(
            alignment=alignment,
            source_current_release=current_release,
            projected_source_release=projected_release,
        )

    # project no consulta current: resuelve exactamente el target recibido y trabaja sobre esa release.
    def project(self, target: ProjectionTarget) -> ProjectionExecutionResult[PayloadT]:
        try:
            release, resources = self._source.read_release(
                target.source_key,
                target.source_release,
            )
            self._validate_release(target, release)
            payload = self._builder.build(release=release, resources=resources)
            candidate = ProjectionRecord(
                source_key=target.source_key,
                source_release_id=target.source_release_id,
                source_published_at_utc=target.source_release.published_at_utc,
                projected_at_utc=self._clock(),
                payload=payload,
            )
            saved = self._projection.replace_active(candidate)
            self._validate_saved(target, saved)
            return ProjectionExecutionResult(target=target, projection=saved)
        except ProjectionInvariantError:
            raise
        except Exception as error:
            # El error conserva el target original; un retry posterior usa la misma SourceReleaseRef.
            raise ProjectionExecutionError(
                'Could not project source release',
                target=target,
            ) from error

    @staticmethod
    def _validate_release(
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
    ) -> None:
        # Core rechaza providers Source que devuelvan una release diferente a la solicitada.
        if release.source_key != target.source_key:
            raise ProjectionInvariantError('Source store returned a different source key')
        if release.release_ref != target.source_release:
            raise ProjectionInvariantError('Source store returned a different source release')

    @staticmethod
    def _validate_saved(
        target: ProjectionTarget,
        projection: ProjectionRecord[PayloadT],
    ) -> None:
        # El store de Projection debe confirmar la misma procedencia que acaba de persistir.
        if projection.source_key != target.source_key:
            raise ProjectionInvariantError('Projection store persisted a different source key')
        if projection.source_release != target.source_release:
            raise ProjectionInvariantError('Projection store persisted a different source release')


def _utc_now() -> datetime:
    return datetime.now(UTC)
