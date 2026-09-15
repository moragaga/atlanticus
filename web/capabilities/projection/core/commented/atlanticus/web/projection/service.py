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
ProjectionDependencySelector = Callable[[SourceKey], tuple[ProjectionTarget, ...]]


# El builder recibe el target exacto para que un dominio pueda resolver sus dependencias sin revision strings.
class ProjectionBuilder(Protocol[PayloadT]):
    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> PayloadT: ...


class SourceProjectionService(Generic[PayloadT]):
    def __init__(
        self,
        *,
        source: SourceStore,
        projection: ProjectionStore[PayloadT],
        builder: ProjectionBuilder[PayloadT],
        dependency_selector: ProjectionDependencySelector | None = None,
        clock: ProjectionClock | None = None,
    ) -> None:
        self._source = source
        self._projection = projection
        self._builder = builder
        self._dependency_selector = dependency_selector or _no_dependencies
        self._clock = clock or _utc_now

    # Current se observa una sola vez para construir una identidad inmutable de ejecución.
    def select_current_target(self, source_key: SourceKey) -> ProjectionTarget | None:
        snapshot = self._source.get_current(source_key)
        if snapshot.current is None:
            return None
        return ProjectionTarget(
            source_key=source_key,
            source_release=snapshot.current.release_ref,
            dependencies=self._dependency_selector(source_key),
        )

    # Una proyección deja de estar CURRENT si cambia su fuente o cualquiera de sus dependencias exactas.
    def get_status(self, source_key: SourceKey) -> ProjectionStatus:
        current_target = self.select_current_target(source_key)
        active = self._projection.get_active(source_key)
        if active is None:
            return ProjectionStatus(
                alignment=ProjectionAlignment.NEVER_PROJECTED,
                source_current_release=(
                    current_target.source_release if current_target is not None else None
                ),
                projected_source_release=None,
                current_dependencies=(
                    current_target.dependencies if current_target is not None else ()
                ),
            )
        if active.source_key != source_key:
            raise ProjectionInvariantError('Projection store returned a different source key')
        projected_target = active.target
        alignment = (
            ProjectionAlignment.CURRENT
            if current_target is not None and projected_target == current_target
            else ProjectionAlignment.OUTDATED
        )
        return ProjectionStatus(
            alignment=alignment,
            source_current_release=(
                current_target.source_release if current_target is not None else None
            ),
            projected_source_release=projected_target.source_release,
            current_dependencies=(current_target.dependencies if current_target is not None else ()),
            projected_dependencies=projected_target.dependencies,
        )

    # project sigue siendo exact-target: no reemplaza el target recibido por current.
    def project(self, target: ProjectionTarget) -> ProjectionExecutionResult[PayloadT]:
        try:
            release, resources = self._source.read_release(
                target.source_key,
                target.source_release,
            )
            self._validate_release(target, release)
            payload = self._builder.build(
                target=target,
                release=release,
                resources=resources,
            )
            candidate = ProjectionRecord(
                source_key=target.source_key,
                source_release_id=target.source_release_id,
                source_published_at_utc=target.source_release.published_at_utc,
                projected_at_utc=self._clock(),
                payload=payload,
                dependencies=target.dependencies,
            )
            saved = self._projection.replace_active(candidate)
            self._validate_saved(target, saved)
            return ProjectionExecutionResult(target=target, projection=saved)
        except ProjectionInvariantError:
            raise
        except Exception as error:
            raise ProjectionExecutionError(
                'Could not project source release',
                target=target,
            ) from error

    @staticmethod
    def _validate_release(
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
    ) -> None:
        if release.source_key != target.source_key:
            raise ProjectionInvariantError('Source store returned a different source key')
        if release.release_ref != target.source_release:
            raise ProjectionInvariantError('Source store returned a different source release')

    @staticmethod
    def _validate_saved(
        target: ProjectionTarget,
        projection: ProjectionRecord[PayloadT],
    ) -> None:
        # El store debe persistir la identidad completa, incluidas dependencias.
        if projection.target != target:
            raise ProjectionInvariantError('Projection store persisted a different projection target')


def _no_dependencies(_source_key: SourceKey) -> tuple[ProjectionTarget, ...]:
    return ()


def _utc_now() -> datetime:
    return datetime.now(UTC)
