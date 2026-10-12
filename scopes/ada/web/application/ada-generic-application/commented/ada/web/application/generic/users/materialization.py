from __future__ import annotations

import logging
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


_LOGGER = logging.getLogger(__name__)


class UsersMaterializationError(RuntimeError):
    pass


class RuntimeUserWriter(Protocol):
    def upsert_base_user(self, user: RuntimeUser) -> RuntimeUser: ...
    def upsert_operational(self, user_id: str, operational: RuntimeOperational) -> RuntimeUser: ...


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


# Composición ADA: las fuentes durables alimentan una sola representación RuntimeUser.
# La materialización base no depende de los datos operacionales de ADA.
class AdaUsersRuntimeMaterializer:
    def __init__(self, *, stores: ConfigurationManagerStores) -> None:
        self._stores = stores
        self._operational_source = (
            OperationalSourceService(store=stores.operational_source)
            if stores.operational_source is not None
            else None
        )

    def materialize_base_user(self, user_id: str) -> RuntimeUser:
        stores = self._stores
        registry = stores.users_registry.load()
        memberships = stores.users_memberships.load()
        identity = registry.get(user_id)
        membership = memberships.get(user_id)
        if identity is None or membership is None:
            raise UsersMaterializationError('Tool membership is missing its global identity')
        profiles_snapshot = stores.profiles_source.get_current(PROFILES_CONFIGURATION_SOURCE_KEY)
        profiles_record = stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        if profiles_snapshot.current is None:
            if profiles_record is not None:
                raise UsersMaterializationError('Profiles projection has no source')
            profiles = ProfileCatalog()
        else:
            if (
                profiles_record is None
                or profiles_record.source_release != profiles_snapshot.current.release_ref
                or not isinstance(profiles_record.payload, ProfileCatalog)
            ):
                raise UsersMaterializationError('A current Profiles projection is required')
            profiles = profiles_record.payload
        profile = require_managed_profile(membership.profile_key, profiles=profiles)
        access_keys = self._optional_access(profile.key, profiles, profiles_record)
        user = build_runtime_user(
            identity=identity,
            membership=membership,
            profile=profile,
            access_keys=access_keys,
        )
        if (
            stores.users_registry.load() != registry
            or stores.users_memberships.load() != memberships
            or stores.profiles_source.get_current(PROFILES_CONFIGURATION_SOURCE_KEY)
            != profiles_snapshot
            or not _same_profiles_record(
                stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY), profiles_record
            )
        ):
            raise UsersMaterializationError('Base user sources changed during resolution')
        return user

    # Si Access no está listo, la publicación base conserva el perfil y deniega grants.
    def _optional_access(
        self, profile_key: str, profiles: ProfileCatalog, profiles_record: ProjectionRecord[ProfileCatalog] | None
    ) -> tuple[str, ...]:
        try:
            source = self._stores.access_source.get_current(ADA_ACCESS_SOURCE_KEY)
            projected = self._stores.access.get_active(ADA_ACCESS_SOURCE_KEY)
            if source.current is None:
                return ()
            if (
                projected is None
                or projected.source_release != source.current.release_ref
                or profiles_record is None
                or projected.dependencies != (profiles_record.target,)
                or not isinstance(projected.payload, AdaAccessConfiguration)
            ):
                return ()
            projected.payload.validate_profiles(profiles)
            keys = tuple(sorted(projected.payload.resolve(profile_key, profiles=profiles).access_keys))
            if (
                self._stores.access_source.get_current(ADA_ACCESS_SOURCE_KEY) != source
                or self._stores.access.get_active(ADA_ACCESS_SOURCE_KEY) != projected
            ):
                return ()
            return keys
        except Exception as error:
            _LOGGER.warning('ADA optional access enrichment unavailable (%s)', type(error).__name__)
            return ()

    def materialize_user(self, user_id: str) -> RuntimeUser:
        context = self._context()
        if context.memberships.get(user_id) is None:
            raise UsersMaterializationError('User does not have a Tool membership')
        user, assignment_state = self._build_user(context, user_id)
        self._verify(context, {user_id: assignment_state})
        return user

    # Reconstrucción explícita: requiere todos los dominios para generar el snapshot completo.
    def materialize_all(self) -> tuple[RuntimeUser, ...]:
        context = self._context()
        assignments: dict[str, SourceSnapshot] = {}
        users: list[RuntimeUser] = []
        for membership in context.memberships.memberships:
            user, assignment_state = self._build_user(context, membership.user_id)
            users.append(user)
            assignments[membership.user_id] = assignment_state
        self._verify(context, assignments)
        return tuple(sorted(users, key=lambda item: item.user_id))

    def publish_user(self, user_id: str, *, writer: RuntimeUserWriter) -> RuntimeUser:
        base = self.materialize_base_user(user_id)
        persisted = writer.upsert_base_user(base)
        if (
            not isinstance(persisted, RuntimeUser)
            or persisted.identity != base.identity
            or persisted.enabled != base.enabled
            or persisted.profile != base.profile
        ):
            raise UsersMaterializationError('Persisted base user differs from materialized user')
        return persisted

    # La publicación operacional se aplica a un usuario existente, de manera aditiva.
    def publish_operational(self, user_id: str, *, writer: RuntimeUserWriter) -> RuntimeUser:
        if self._operational_source is None or self._stores.operational is None:
            raise UsersMaterializationError('Operational enrichment is not configured')
        memberships = self._stores.users_memberships.load()
        if memberships.get(user_id) is None:
            raise UsersMaterializationError('User does not have a Tool membership')
        key = assignment_source_key(user_id)
        snapshot, assignment = self._operational_source.current(key)
        if assignment is None:
            assignment = OperationalAssignment(user_id=user_id)
        if not isinstance(assignment, OperationalAssignment) or assignment.user_id != user_id:
            raise UsersMaterializationError('Operational assignment is invalid')
        catalog_snapshot = self._operational_source.snapshot(CATALOG_SOURCE_KEY)
        catalog_record = self._stores.operational.get_active(CATALOG_SOURCE_KEY)
        if catalog_snapshot.current is None:
            if catalog_record is not None:
                raise UsersMaterializationError('Operational catalog projection has no source')
            catalog = OperationalCatalog()
        elif (
            catalog_record is None
            or catalog_record.source_release != catalog_snapshot.current.release_ref
            or not isinstance(catalog_record.payload, OperationalCatalog)
        ):
            raise UsersMaterializationError('A current Operational catalog projection is required')
        else:
            catalog = catalog_record.payload
        operational = _resolve_operational(assignment, catalog)
        if (
            self._stores.users_memberships.load() != memberships
            or self._operational_source.snapshot(key) != snapshot
            or self._operational_source.snapshot(CATALOG_SOURCE_KEY) != catalog_snapshot
            or self._stores.operational.get_active(CATALOG_SOURCE_KEY) != catalog_record
        ):
            raise UsersMaterializationError('Operational enrichment changed during resolution')
        update = getattr(writer, 'upsert_operational', None)
        if not callable(update):
            raise TypeError('Operational writer must support partial operational publication')
        persisted = update(user_id, operational)
        if not isinstance(persisted, RuntimeUser) or persisted.user_id != user_id or persisted.operational != operational:
            raise UsersMaterializationError('Persisted operational enrichment differs from request')
        return persisted

    def _context(self) -> _Context:
        if self._operational_source is None or self._stores.operational is None:
            raise UsersMaterializationError('Operational reconstruction is not configured')
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
        if self._operational_source is None:
            raise UsersMaterializationError('Operational reconstruction is not configured')
        membership = context.memberships.get(user_id)
        identity = context.registry.get(user_id)
        if membership is None or identity is None:
            raise UsersMaterializationError('Tool membership is missing its global identity')
        profile = require_managed_profile(membership.profile_key, profiles=context.profiles_record.payload)
        access = context.access_record.payload.resolve(profile.key, profiles=context.profiles_record.payload)
        source_key = assignment_source_key(user_id)
        snapshot, assignment = self._operational_source.current(source_key)
        if assignment is None:
            assignment = OperationalAssignment(user_id=user_id)
        if not isinstance(assignment, OperationalAssignment) or assignment.user_id != user_id:
            raise UsersMaterializationError('Operational assignment source is invalid')
        operational = _resolve_operational(assignment, context.catalog)
        user = build_runtime_user(
            identity=identity,
            membership=membership,
            profile=profile,
            access_keys=tuple(sorted(access.access_keys)),
            operational=operational,
        )
        return user, snapshot

    # Verifica cambios de Source sin comparar por identidad objetos rehidratados de Cosmos.
    def _verify(self, context: _Context, assignments: dict[str, SourceSnapshot]) -> None:
        stores = self._stores
        if (
            stores.users_registry.load() != context.registry
            or stores.users_memberships.load() != context.memberships
            or stores.profiles_source.get_current(PROFILES_CONFIGURATION_SOURCE_KEY) != context.profiles_snapshot
            or stores.access_source.get_current(ADA_ACCESS_SOURCE_KEY) != context.access_snapshot
            or self._operational_source.snapshot(CATALOG_SOURCE_KEY) != context.catalog_snapshot
            or not _same_profiles_record(
                stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY), context.profiles_record
            )
            or stores.access.get_active(ADA_ACCESS_SOURCE_KEY) != context.access_record
            or stores.operational.get_active(CATALOG_SOURCE_KEY) != context.catalog_record
        ):
            raise UsersMaterializationError('Users materialization sources changed during resolution')
        for user_id, snapshot in assignments.items():
            if self._operational_source.snapshot(assignment_source_key(user_id)) != snapshot:
                raise UsersMaterializationError('Operational assignment changed during resolution')


def _same_profiles_record(
    left: ProjectionRecord[ProfileCatalog] | None,
    right: ProjectionRecord[ProfileCatalog] | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return (
        isinstance(left.payload, ProfileCatalog)
        and isinstance(right.payload, ProfileCatalog)
        and left.target == right.target
        and getattr(left, 'projected_at_utc', None) == getattr(right, 'projected_at_utc', None)
        and left.payload.all() == right.payload.all()
    )


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
