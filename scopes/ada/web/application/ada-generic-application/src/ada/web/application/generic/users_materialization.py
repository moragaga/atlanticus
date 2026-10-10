from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ada.web.access.configuration import ADA_ACCESS_SOURCE_KEY, AdaAccessConfiguration
from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    assignment_source_key,
)
from ada.web.operational.identification.source import OperationalSourceService
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceSnapshot
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeUser,
    ToolMembershipSnapshot,
    UsersRegistrySnapshot,
    build_runtime_user,
)
from atlanticus.web.users.profiles import require_managed_profile


class UsersMaterializationError(RuntimeError):
    pass


class RuntimeUserWriter(Protocol):
    def upsert_user(self, user: RuntimeUser) -> RuntimeUser: ...


@dataclass(frozen=True, slots=True)
class _Context:
    registry: UsersRegistrySnapshot
    memberships: ToolMembershipSnapshot
    profiles_snapshot: SourceSnapshot
    access_snapshot: SourceSnapshot
    catalog_snapshot: SourceSnapshot
    profiles_record: ProjectionRecord[ProfileCatalog]
    access_record: ProjectionRecord[AdaAccessConfiguration]
    catalog_record: ProjectionRecord[OperationalCatalog] | None
    catalog: OperationalCatalog


class AdaUsersRuntimeMaterializer:
    def __init__(self, *, stores: ConfigurationManagerStores) -> None:
        if stores.operational_source is None or stores.operational is None:
            raise UsersMaterializationError('Operational stores are required to materialize users')
        self._stores = stores
        self._operational_source = OperationalSourceService(store=stores.operational_source)

    def materialize_user(self, user_id: str) -> RuntimeUser:
        context = self._context()
        if context.memberships.get(user_id) is None:
            raise UsersMaterializationError('User does not have a Tool membership')
        user, assignment_snapshot = self._build_user(context, user_id)
        self._verify(context, {user_id: assignment_snapshot})
        return user

    def materialize_all(self) -> tuple[RuntimeUser, ...]:
        context = self._context()
        assignments: dict[str, SourceSnapshot] = {}
        users: list[RuntimeUser] = []
        for membership in context.memberships.memberships:
            user, assignment_snapshot = self._build_user(context, membership.user_id)
            users.append(user)
            assignments[membership.user_id] = assignment_snapshot
        self._verify(context, assignments)
        return tuple(sorted(users, key=lambda item: item.user_id))

    def publish_user(self, user_id: str, *, writer: RuntimeUserWriter) -> RuntimeUser:
        user = self.materialize_user(user_id)
        persisted = writer.upsert_user(user)
        if persisted != user:
            raise UsersMaterializationError('Persisted runtime user differs from materialized user')
        return persisted

    def _context(self) -> _Context:
        stores = self._stores
        registry = stores.users_registry.load()
        memberships = stores.users_memberships.load()
        profiles_snapshot = stores.profiles_source.get_current(PROFILES_CONFIGURATION_SOURCE_KEY)
        access_snapshot = stores.access_source.get_current(ADA_ACCESS_SOURCE_KEY)
        catalog_snapshot = self._operational_source.snapshot(CATALOG_SOURCE_KEY)
        profiles_record = stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        access_record = stores.access.get_active(ADA_ACCESS_SOURCE_KEY)
        catalog_record = stores.operational.get_active(CATALOG_SOURCE_KEY)
        if (
            profiles_snapshot.current is None
            or profiles_record is None
            or profiles_record.source_release != profiles_snapshot.current.release_ref
            or not isinstance(profiles_record.payload, ProfileCatalog)
        ):
            raise UsersMaterializationError('A current Profiles projection is required')
        if (
            access_snapshot.current is None
            or access_record is None
            or access_record.source_release != access_snapshot.current.release_ref
            or not isinstance(access_record.payload, AdaAccessConfiguration)
            or access_record.dependencies != (profiles_record.target,)
        ):
            raise UsersMaterializationError('A current Access projection for Profiles is required')
        if catalog_snapshot.current is None:
            if catalog_record is not None:
                raise UsersMaterializationError('Operational catalog projection has no source')
            catalog = OperationalCatalog()
        else:
            if (
                catalog_record is None
                or catalog_record.source_release != catalog_snapshot.current.release_ref
                or not isinstance(catalog_record.payload, OperationalCatalog)
            ):
                raise UsersMaterializationError('A current Operational catalog projection is required')
            catalog = catalog_record.payload
        access_record.payload.validate_profiles(profiles_record.payload)
        return _Context(
            registry=registry,
            memberships=memberships,
            profiles_snapshot=profiles_snapshot,
            access_snapshot=access_snapshot,
            catalog_snapshot=catalog_snapshot,
            profiles_record=profiles_record,
            access_record=access_record,
            catalog_record=catalog_record,
            catalog=catalog,
        )

    def _build_user(self, context: _Context, user_id: str) -> tuple[RuntimeUser, SourceSnapshot]:
        membership = context.memberships.get(user_id)
        identity = context.registry.get(user_id)
        if membership is None or identity is None:
            raise UsersMaterializationError('Tool membership is missing its global identity')
        profile = require_managed_profile(membership.profile_key, profiles=context.profiles_record.payload)
        access = context.access_record.payload.resolve(profile.key, profiles=context.profiles_record.payload)
        source_key = assignment_source_key(user_id)
        snapshot, payload = self._operational_source.current(source_key)
        if payload is None:
            assignment = OperationalAssignment(user_id=user_id)
        elif isinstance(payload, OperationalAssignment) and payload.user_id == user_id:
            assignment = payload
        else:
            raise UsersMaterializationError('Operational assignment does not match the user')
        operational = _resolve_operational(assignment, context.catalog)
        user = build_runtime_user(
            identity=identity,
            membership=membership,
            profile=profile,
            access_keys=tuple(sorted(access.access_keys)),
            operational=operational,
        )
        return user, snapshot

    def _verify(self, context: _Context, assignments: dict[str, SourceSnapshot]) -> None:
        stores = self._stores
        if (
            stores.users_registry.load() != context.registry
            or stores.users_memberships.load() != context.memberships
            or stores.profiles_source.get_current(PROFILES_CONFIGURATION_SOURCE_KEY)
            != context.profiles_snapshot
            or stores.access_source.get_current(ADA_ACCESS_SOURCE_KEY) != context.access_snapshot
            or self._operational_source.snapshot(CATALOG_SOURCE_KEY) != context.catalog_snapshot
            or stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY) != context.profiles_record
            or stores.access.get_active(ADA_ACCESS_SOURCE_KEY) != context.access_record
            or stores.operational.get_active(CATALOG_SOURCE_KEY) != context.catalog_record
        ):
            raise UsersMaterializationError('Users materialization sources changed during resolution')
        for user_id, snapshot in assignments.items():
            if self._operational_source.snapshot(assignment_source_key(user_id)) != snapshot:
                raise UsersMaterializationError('Operational assignment changed during resolution')


def _resolve_operational(
    assignment: OperationalAssignment,
    catalog: OperationalCatalog,
) -> RuntimeOperational:
    data = catalog.to_document()
    areas = {item['id']: item['label'] for item in data['areas']}
    groups = {item['id']: item['label'] for item in data['groups']}
    position = None
    if assignment.position_id is not None:
        item = catalog.position(assignment.position_id)
        if item is None:
            raise UsersMaterializationError('Operational position is missing from the catalog')
        position = RuntimeOperationalReference(id=item.id, label=item.label)
    return RuntimeOperational(
        area=(
            None if assignment.area_id is None
            else RuntimeOperationalReference(id=assignment.area_id, label=areas[assignment.area_id])
        ),
        position=position,
        group=(
            None if assignment.group_id is None
            else RuntimeOperationalReference(id=assignment.group_id, label=groups[assignment.group_id])
        ),
    )
