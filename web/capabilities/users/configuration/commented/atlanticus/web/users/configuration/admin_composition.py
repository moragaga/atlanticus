from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationSourceError,
    UsersConfigurationValidationError,
)
from atlanticus.web.users.configuration.models import UserConfiguration, build_profile_key
from atlanticus.web.users.configuration.source_release import UsersSourceService
from atlanticus.web.users.models import PendingUserRecord
from atlanticus.web.users.store import PendingUsersReader

# Administrator ya es un Profile funcional explícito. Estos defaults conservan únicamente
# el baseline visual vigente cuando todavía no existe ninguna release publicada.
_ADMINISTRATOR_PROFILE_KEY = 'administrator'
_DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR = '#673AB7'
_DEFAULT_ADMINISTRATOR_TEXT_COLOR = '#FFFFFF'
_ADMIN_DRAFT_DOCUMENT_TYPE = 'atlanticus_users_profiles_admin_draft'
_ADMIN_DRAFT_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class UsersProfilesAdminState:
    # La configuración puede ser None cuando Source aún no tiene una release.
    configuration: UsersProfilesConfiguration | None
    # El snapshot exacto se conserva para usar su token CAS y su basis release al publicar.
    source_snapshot: SourceSnapshot


@dataclass(frozen=True, slots=True)
class UsersProfilesAdminDraft:
    owner_subject_id: str
    configuration: UsersProfilesConfiguration
    source_snapshot: SourceSnapshot
    revision: str
    # Revisión local del contenido exacto que constituía la BASE al crear o rebasar el draft.
    # No es SourceReleaseId ni ConcurrencyToken.
    base_payload_revision: str
    saved_at_utc: datetime

    def __post_init__(self) -> None:
        # La revisión identifica sólo el contenido del borrador local. No representa una
        # SourceReleaseId y por eso nunca se convierte en identidad de release.
        owner = self.owner_subject_id.strip()
        expected_revision = build_users_profiles_admin_revision(self.configuration)
        if not owner:
            raise UsersConfigurationValidationError('Users admin draft owner must not be empty')
        if self.revision.strip() != expected_revision:
            raise UsersConfigurationValidationError(
                'Users admin draft revision does not match content'
            )
        base_payload_revision = self.base_payload_revision.strip()
        if not base_payload_revision:
            raise UsersConfigurationValidationError(
                'Users admin draft base payload revision must not be empty'
            )
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise UsersConfigurationValidationError(
                'Users admin draft timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'owner_subject_id', owner)
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'base_payload_revision', base_payload_revision)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        owner_subject_id: str,
        configuration: UsersProfilesConfiguration,
        source_snapshot: SourceSnapshot,
        saved_at_utc: datetime | None = None,
    ) -> UsersProfilesAdminDraft:
        # Un draft recién creado nace limpio: la revisión actual y la BASE local son iguales.
        # La identidad Source se conserva por separado en el snapshot exacto.
        revision = build_users_profiles_admin_revision(configuration)
        return cls(
            owner_subject_id=owner_subject_id,
            configuration=configuration,
            source_snapshot=source_snapshot,
            revision=revision,
            base_payload_revision=revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
        )

    @property
    def has_local_changes(self) -> bool:
        # La suciedad funcional depende sólo de dos identidades locales de payload.
        # Source puede refrescar su token sin convertir por eso el contenido local en modificado.
        return self.revision != self.base_payload_revision

    def with_configuration(
        self,
        configuration: UsersProfilesConfiguration,
        *,
        saved_at_utc: datetime | None = None,
    ) -> UsersProfilesAdminDraft:
        # Editar reemplaza el contenido actual y recalcula revision, pero conserva tanto
        # la BASE local como el SourceSnapshot exacto con el que nació el trabajo.
        return UsersProfilesAdminDraft(
            owner_subject_id=self.owner_subject_id,
            configuration=configuration,
            source_snapshot=self.source_snapshot,
            revision=build_users_profiles_admin_revision(configuration),
            base_payload_revision=self.base_payload_revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
        )

    def rebase(
        self,
        source_snapshot: SourceSnapshot,
        *,
        saved_at_utc: datetime | None = None,
    ) -> UsersProfilesAdminDraft:
        # Rebase sólo debe usarse cuando un nuevo SourceSnapshot ya fue confirmado por el
        # flujo de publicación. El contenido actual pasa a ser la nueva BASE local sin mutarlo.
        return UsersProfilesAdminDraft(
            owner_subject_id=self.owner_subject_id,
            configuration=self.configuration,
            source_snapshot=source_snapshot,
            revision=self.revision,
            base_payload_revision=self.revision,
            saved_at_utc=(saved_at_utc or datetime.now(UTC)).astimezone(UTC),
        )

    def to_document(self) -> dict[str, object]:
        # El payload durable del borrador usa directamente el contrato de composición
        # canónico, sin reconstruir UsersConfigurationCatalog.
        return {
            'document_type': _ADMIN_DRAFT_DOCUMENT_TYPE,
            'schema_version': _ADMIN_DRAFT_SCHEMA_VERSION,
            'owner_subject_id': self.owner_subject_id,
            'revision': self.revision,
            'base_payload_revision': self.base_payload_revision,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'source_snapshot': _source_snapshot_to_document(self.source_snapshot),
            'payload': self.configuration.to_document(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersProfilesAdminDraft:
        try:
            # No se aceptan schemas de borrador legacy: el estado de navegador es transitorio
            # y este incremento hace un cutover limpio del authoring activo.
            if (
                document.get('document_type') != _ADMIN_DRAFT_DOCUMENT_TYPE
                or document.get('schema_version') != _ADMIN_DRAFT_SCHEMA_VERSION
            ):
                raise TypeError
            payload = document['payload']
            snapshot = document['source_snapshot']
            if not isinstance(payload, dict) or not isinstance(snapshot, dict):
                raise TypeError
            return cls(
                owner_subject_id=str(document['owner_subject_id']),
                configuration=UsersProfilesConfiguration.from_document(dict(payload)),
                source_snapshot=_source_snapshot_from_document(dict(snapshot)),
                revision=str(document['revision']),
                base_payload_revision=str(document['base_payload_revision']),
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
            )
        except (KeyError, TypeError, ValueError, UsersConfigurationValidationError) as error:
            raise UsersConfigurationValidationError('Users admin draft contract is invalid') from error


class UsersProfilesAdministrationService:
    def __init__(
        self,
        *,
        source: UsersSourceService,
        pending: PendingUsersReader,
    ) -> None:
        self._source = source
        self._pending = pending

    def get_source_snapshot(self) -> SourceSnapshot:
        # Manager puede pedir sólo la base exacta sin cargar/decodificar la release.
        return self._source.get_current()

    def load_current(self) -> UsersProfilesAdminState:
        # Primero se captura current y luego se lee exactamente esa release. Un segundo read
        # de current detecta si hubo una carrera mientras se construía el estado del editor.
        snapshot = self.get_source_snapshot()
        if snapshot.current is None:
            return UsersProfilesAdminState(configuration=None, source_snapshot=snapshot)
        release = self._source.load_release(snapshot.current.release_ref)
        refreshed = self._source.get_current()
        if refreshed != snapshot:
            raise UsersConfigurationSourceError('Users source changed while it was being loaded')
        return UsersProfilesAdminState(
            configuration=release.payload.projection_payload(),
            source_snapshot=snapshot,
        )

    def create_draft(self, *, owner_subject_id: str) -> UsersProfilesAdminDraft:
        state = self.load_current()
        return UsersProfilesAdminDraft.create(
            owner_subject_id=owner_subject_id,
            configuration=state.configuration or default_users_profiles_configuration(),
            source_snapshot=state.source_snapshot,
        )

    def list_pending(
        self,
        configuration: UsersProfilesConfiguration,
    ) -> tuple[PendingUserRecord, ...]:
        # Pending sigue siendo Users-owned. Sólo se ocultan identidades que ya están
        # configuradas en el snapshot que el administrador está editando.
        configured = configuration.users.users
        return tuple(
            pending
            for pending in self._pending.list_pending()
            if not any(_matches_configured_identity(pending, user) for user in configured)
        )

    def publish(
        self,
        configuration: UsersProfilesConfiguration,
        *,
        expected_source_snapshot: SourceSnapshot,
        published_by: str,
    ) -> PublishResult:
        # Nunca se compara una revisión textual con una SourceReleaseId. Se exige el snapshot
        # exacto y el SourceStore hace el CAS final con su ConcurrencyToken.
        if expected_source_snapshot.source_key != self._source.source_key:
            raise UsersConfigurationSourceError('Users source snapshot uses a different source key')
        current = self._source.get_current()
        if current != expected_source_snapshot:
            raise UsersConfigurationSourceError('Users source changed before publication')
        actor = published_by.strip()
        if not actor:
            raise UsersConfigurationSourceError('Users source publication actor must not be empty')
        basis_release = (
            expected_source_snapshot.current.release_ref
            if expected_source_snapshot.current is not None
            else None
        )
        return self._source.publish_configuration(
            configuration.users,
            configuration.profiles,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=basis_release,
        )

    def publish_draft(
        self,
        draft: UsersProfilesAdminDraft,
        *,
        published_by: str,
    ) -> PublishResult:
        return self.publish(
            draft.configuration,
            expected_source_snapshot=draft.source_snapshot,
            published_by=published_by,
        )


def default_users_profiles_configuration() -> UsersProfilesConfiguration:
    # Un editor vacío sigue siendo contractualmente válido porque Administrator debe existir.
    administrator = ProfileDefinition(
        key=_ADMINISTRATOR_PROFILE_KEY,
        label='Administrador',
        background_color=_DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
        text_color=_DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(),
        profiles=ProfilesConfiguration(profiles=(administrator,)),
    )


def build_users_profiles_admin_revision(configuration: UsersProfilesConfiguration) -> str:
    # Hash local determinista para detectar cambios/integridad del draft. No es release id.
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def update_administrator_colors(
    configuration: UsersProfilesConfiguration,
    *,
    background_color: str,
    text_color: str,
) -> UsersProfilesConfiguration:
    profiles = configuration.profiles.catalog()
    administrator = profiles.require(_ADMINISTRATOR_PROFILE_KEY)
    updated = ProfileDefinition(
        key=administrator.key,
        label=administrator.label,
        background_color=background_color,
        text_color=text_color,
    )
    return _replace_profile(configuration, updated)


def save_functional_profile(
    configuration: UsersProfilesConfiguration,
    *,
    original_key: str | None,
    label: str,
    background_color: str,
    text_color: str,
) -> UsersProfilesConfiguration:
    # En creación se genera una key estable. En edición se conserva la key original.
    normalized_label = label.strip()
    if original_key is None:
        key = build_profile_key(normalized_label)
        if any(profile.key == key for profile in configuration.profiles.profiles):
            raise UsersConfigurationValidationError('Profile already exists')
    else:
        existing = configuration.profiles.catalog().require(original_key)
        if existing.key == _ADMINISTRATOR_PROFILE_KEY:
            raise UsersConfigurationValidationError(
                'Administrator profile must be edited through its dedicated operation'
            )
        key = existing.key
    profile = ProfileDefinition(
        key=key,
        label=normalized_label,
        background_color=background_color,
        text_color=text_color,
    )
    if original_key is None:
        profiles = (*configuration.profiles.profiles, profile)
        return UsersProfilesConfiguration(
            users=configuration.users,
            profiles=ProfilesConfiguration(profiles=profiles),
        )
    return _replace_profile(configuration, profile)


def delete_functional_profile(
    configuration: UsersProfilesConfiguration,
    profile_key: str,
    *,
    replacement_profile_key: str | None = None,
) -> UsersProfilesConfiguration:
    # La operación trabaja sobre el snapshot completo para que nunca exista un estado
    # intermedio con Users huérfanos.
    catalog = configuration.profiles.catalog()
    profile = catalog.require(profile_key)
    if profile.key == _ADMINISTRATOR_PROFILE_KEY:
        raise UsersConfigurationValidationError('Administrator profile cannot be deleted')
    referenced = tuple(
        user for user in configuration.users.users if user.profile_key == profile.key
    )
    replacement = None
    if referenced:
        if replacement_profile_key is None:
            raise UsersConfigurationValidationError(
                'Referenced profile requires reassignment before deletion'
            )
        replacement = catalog.require(replacement_profile_key)
        if replacement.key == profile.key:
            raise UsersConfigurationValidationError(
                'Replacement profile must be different from deleted profile'
            )
    users = configuration.users.users
    if replacement is not None:
        users = tuple(
            replace(user, profile_key=replacement.key) if user.profile_key == profile.key else user
            for user in users
        )
    profiles = tuple(
        current for current in configuration.profiles.profiles if current.key != profile.key
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(users=users),
        profiles=ProfilesConfiguration(profiles=profiles),
    )


def add_pending_user(
    configuration: UsersProfilesConfiguration,
    pending: PendingUserRecord,
    *,
    display_name: str,
    email: str | None,
    profile_key: str,
    enabled: bool = True,
) -> UsersProfilesConfiguration:
    # La única creación administrativa admitida parte de una identidad Pending observada.
    if any(
        user.user_id == pending.user_id
        or (user.issuer, user.subject_id) == (pending.issuer, pending.subject_id)
        for user in configuration.users.users
    ):
        raise UsersConfigurationValidationError('User already exists')
    user = UserConfiguration.create(
        user_id=pending.user_id,
        issuer=pending.issuer,
        subject_id=pending.subject_id,
        display_name=display_name,
        email=email,
        profile_key=profile_key,
        enabled=enabled,
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(users=(*configuration.users.users, user)),
        profiles=configuration.profiles,
    )


def update_managed_user(
    configuration: UsersProfilesConfiguration,
    user: UserConfiguration,
) -> UsersProfilesConfiguration:
    # Editar un Managed User no permite reemplazar su identidad autenticada.
    existing = next(
        (current for current in configuration.users.users if current.user_id == user.user_id),
        None,
    )
    if existing is None:
        raise UsersConfigurationValidationError('User does not exist')
    if (existing.issuer, existing.subject_id) != (user.issuer, user.subject_id):
        raise UsersConfigurationValidationError('Managed user identity cannot be changed')
    users = tuple(
        user if current.user_id == user.user_id else current
        for current in configuration.users.users
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(users=users),
        profiles=configuration.profiles,
    )


def _replace_profile(
    configuration: UsersProfilesConfiguration,
    profile: ProfileDefinition,
) -> UsersProfilesConfiguration:
    profiles = tuple(
        profile if current.key == profile.key else current
        for current in configuration.profiles.profiles
    )
    if not any(current.key == profile.key for current in configuration.profiles.profiles):
        raise UsersConfigurationValidationError('Profile does not exist')
    return UsersProfilesConfiguration(
        users=configuration.users,
        profiles=ProfilesConfiguration(profiles=profiles),
    )


def _matches_configured_identity(
    pending: PendingUserRecord,
    configured: UserConfiguration,
) -> bool:
    return pending.issuer == configured.issuer and pending.subject_id == configured.subject_id


def _source_snapshot_to_document(snapshot: SourceSnapshot) -> dict[str, object]:
    # El snapshot se serializa completo para poder reconstruir la misma base exacta de
    # publicación después de persistir/restaurar el borrador del navegador.
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


def _source_snapshot_from_document(document: dict[str, Any]) -> SourceSnapshot:
    current_document = document.get('current')
    token_value = document.get('concurrency_token')
    current = None
    if current_document is not None:
        if not isinstance(current_document, dict):
            raise TypeError
        content_hash = current_document['content_hash']
        if not isinstance(content_hash, dict):
            raise TypeError
        current = SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(str(current_document['release_id'])),
                published_at_utc=datetime.fromisoformat(
                    str(current_document['published_at_utc'])
                ),
            ),
            content_hash=Digest(
                algorithm=str(content_hash['algorithm']),
                value=str(content_hash['value']),
            ),
        )
    return SourceSnapshot(
        source_key=SourceKey(str(document['source_key'])),
        current=current,
        concurrency_token=(
            ConcurrencyToken(str(token_value)) if token_value is not None else None
        ),
    )
