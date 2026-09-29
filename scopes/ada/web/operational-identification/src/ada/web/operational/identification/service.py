from __future__ import annotations

from ada.web.operational.identification.errors import OperationalReferenceError
from ada.web.operational.identification.keys import (
    CATALOG_SOURCE_KEY,
    assignment_source_key,
    source_kind,
)
from ada.web.operational.identification.models import (
    OperationalAssignment,
    OperationalCatalog,
    OperationalDocument,
)
from ada.web.operational.identification.projection import create_operational_projection_service
from ada.web.operational.identification.source import OperationalSourceService
from atlanticus.web.projection.models import ProjectionRecord, ProjectionStatus
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import PublishResult, SourceKey, SourceSnapshot
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.store import UsersAdministrationStore


class OperationalIdentificationService:
    def __init__(
        self,
        *,
        source_store: SourceStore,
        projections: ProjectionStore[OperationalDocument],
        users: UsersAdministrationStore,
    ) -> None:
        self._source = OperationalSourceService(store=source_store)
        self._projections = projections
        self._users = users
        self._projection: SourceProjectionService[OperationalDocument] = (
            create_operational_projection_service(
                source=source_store,
                projection=projections,
            )
        )

    def catalog_for_edit(self) -> tuple[SourceSnapshot, OperationalCatalog]:
        snapshot, value = self._source.current(CATALOG_SOURCE_KEY)
        if value is None:
            return snapshot, OperationalCatalog()
        if not isinstance(value, OperationalCatalog):
            raise OperationalReferenceError('Operational catalog source has an invalid type')
        return snapshot, value

    def assignment_for_edit(self, user_id: str) -> tuple[SourceSnapshot, OperationalAssignment]:
        self._require_user(user_id)
        snapshot, value = self._source.current(assignment_source_key(user_id))
        if value is None:
            return snapshot, OperationalAssignment(user_id=user_id)
        if not isinstance(value, OperationalAssignment) or value.user_id != user_id:
            raise OperationalReferenceError('Operational assignment source has an invalid type')
        return snapshot, value

    def publish_catalog(
        self,
        catalog: OperationalCatalog,
        *,
        actor: str,
        expected: SourceSnapshot,
    ) -> PublishResult:
        _, previous = self.catalog_for_edit()
        catalog.validate_revision(previous)
        return self._source.publish(catalog, actor=actor, expected=expected)

    def publish_assignment(
        self,
        assignment: OperationalAssignment,
        *,
        actor: str,
        expected: SourceSnapshot,
    ) -> PublishResult:
        self._require_user(assignment.user_id)
        _, catalog = self.catalog_for_edit()
        _, previous = self.assignment_for_edit(assignment.user_id)
        if assignment.position_id is not None:
            catalog.require_position(assignment.position_id, current_id=previous.position_id)
        return self._source.publish(assignment, actor=actor, expected=expected)

    def projection_status(self, source_key: SourceKey) -> ProjectionStatus:
        source_kind(source_key)
        return self._projection.get_status(source_key)

    def project_current(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[OperationalDocument] | None:
        source_kind(source_key)
        target = self._projection.select_current_target(source_key)
        if target is None:
            return None
        previous = self._projections.get_active(source_key)
        if previous is not None and previous.target == target:
            return previous
        return self._projection.project(target).projection

    def catalog_for_read(self) -> OperationalCatalog:
        active = self._projections.get_active(CATALOG_SOURCE_KEY)
        if active is None:
            return OperationalCatalog()
        if not isinstance(active.payload, OperationalCatalog):
            raise OperationalReferenceError('Operational catalog projection has an invalid type')
        return active.payload

    def assignment_for_read(self, user_id: str) -> OperationalAssignment:
        self._require_user(user_id)
        return self._read_projected_assignment(user_id)

    def assignment_for_resolved_user(self, user: EffectiveUser) -> OperationalAssignment:
        if not isinstance(user, EffectiveUser):
            raise TypeError('A resolved effective user is required')
        if not user.enabled or user.profile_key == 'guest':
            raise OperationalReferenceError('Operational user is not authorized')
        if user.is_local:
            return OperationalAssignment(user_id=user.user_id)
        return self._read_projected_assignment(user.user_id)

    def _read_projected_assignment(self, user_id: str) -> OperationalAssignment:
        source_key = assignment_source_key(user_id)
        active = self._projections.get_active(source_key)
        if active is None:
            return OperationalAssignment(user_id=user_id)
        if (
            not isinstance(active.payload, OperationalAssignment)
            or active.payload.user_id != user_id
        ):
            raise OperationalReferenceError('Operational assignment projection has an invalid type')
        return active.payload

    def _require_user(self, user_id: str) -> None:
        assignment_source_key(user_id)
        user = self._users.get(user_id)
        if user is None or user.user_id != user_id:
            raise OperationalReferenceError('User must already be promoted')
