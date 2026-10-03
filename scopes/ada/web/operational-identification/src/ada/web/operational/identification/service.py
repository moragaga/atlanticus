from __future__ import annotations

from uuid import uuid4

from ada.web.operational.identification.errors import OperationalReferenceError
from ada.web.operational.identification.keys import CATALOG_SOURCE_KEY, assignment_source_key, source_kind
from ada.web.operational.identification.models import (
    OperationalAssignment,
    OperationalCatalog,
    OperationalDocument,
    Position,
)
from ada.web.operational.identification.projection import create_operational_projection_service
from ada.web.operational.identification.source import OperationalSourceService
from atlanticus.web.projection.models import ProjectionRecord, ProjectionStatus
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import PublishResult, SourceKey, SourceSnapshot
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeUser,
)
from atlanticus.web.users.store import ToolMembershipStore


class OperationalIdentificationService:
    def __init__(
        self,
        *,
        source_store: SourceStore,
        projections: ProjectionStore[OperationalDocument],
        memberships: ToolMembershipStore,
    ) -> None:
        self._source = OperationalSourceService(store=source_store)
        self._projections = projections
        self._memberships = memberships
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

    def create_position(
        self,
        *,
        label: str,
        active: bool = True,
        actor: str,
        expected: SourceSnapshot,
    ) -> tuple[Position, PublishResult]:
        snapshot, catalog = self.catalog_for_edit()
        if snapshot != expected:
            raise OperationalReferenceError('Operational catalog changed before creating position')
        identifiers = {position.id for position in catalog.positions}
        for _attempt in range(10):
            position_id = f'position_{uuid4().hex}'
            if position_id not in identifiers:
                break
        else:
            raise OperationalReferenceError('Could not generate a unique position identifier')
        position = Position(id=position_id, label=label, active=active)
        updated = OperationalCatalog(positions=(*catalog.positions, position))
        result = self.publish_catalog(updated, actor=actor, expected=expected)
        return position, result

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
        _, previous = self.assignment_for_edit(assignment.user_id)
        if assignment.position_id is not None and assignment.position_id != previous.position_id:
            self._require_projected_position(assignment.position_id)
        return self._source.publish(assignment, actor=actor, expected=expected)

    def _require_projected_position(self, position_id: str) -> None:
        snapshot, _ = self.catalog_for_edit()
        active = self._projections.get_active(CATALOG_SOURCE_KEY)
        if snapshot.current is None or active is None:
            raise OperationalReferenceError(
                'Operational catalog must be projected before assigning positions'
            )
        if active.source_release != snapshot.current.release_ref:
            raise OperationalReferenceError('Operational catalog projection is outdated')
        if not isinstance(active.payload, OperationalCatalog):
            raise OperationalReferenceError('Operational catalog projection has an invalid type')
        active.payload.require_position(position_id)
        if self._source.snapshot(CATALOG_SOURCE_KEY) != snapshot:
            raise OperationalReferenceError('Operational catalog changed before assigning position')

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
        return self._projected_assignment(user_id)

    def assignment_for_resolved_user(self, user: RuntimeUser) -> OperationalAssignment:
        if not isinstance(user, RuntimeUser):
            raise TypeError('A resolved RuntimeUser is required')
        if not user.enabled:
            raise OperationalReferenceError('Operational user is not authorized')
        return OperationalAssignment(
            user_id=user.user_id,
            area_id=None if user.operational.area is None else str(user.operational.area.id),
            position_id=(
                None if user.operational.position is None else str(user.operational.position.id)
            ),
            group_id=(
                None if user.operational.group is None else int(user.operational.group.id)
            ),
        )

    def runtime_snapshot_for_user(self, user_id: str) -> RuntimeOperational:
        self._require_user(user_id)
        assignment = self._projected_assignment(user_id)
        catalog = self.catalog_for_read()
        document = catalog.to_document()
        areas = {item['id']: item['label'] for item in document['areas']}
        groups = {item['id']: item['label'] for item in document['groups']}
        area = (
            None
            if assignment.area_id is None
            else RuntimeOperationalReference(
                id=assignment.area_id,
                label=areas[assignment.area_id],
            )
        )
        position = None
        if assignment.position_id is not None:
            resolved = catalog.position(assignment.position_id)
            if resolved is None:
                raise OperationalReferenceError(
                    'Projected Operational assignment references an unavailable position'
                )
            position = RuntimeOperationalReference(id=resolved.id, label=resolved.label)
        group = (
            None
            if assignment.group_id is None
            else RuntimeOperationalReference(
                id=assignment.group_id,
                label=groups[assignment.group_id],
            )
        )
        return RuntimeOperational(area=area, position=position, group=group)

    def _projected_assignment(self, user_id: str) -> OperationalAssignment:
        active = self._projections.get_active(assignment_source_key(user_id))
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
        membership = self._memberships.load().get(user_id)
        if membership is None:
            raise OperationalReferenceError('User must already have a Tool membership')
