from datetime import UTC, datetime

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)
from atlanticus.web.users.configuration import (
    UserConfiguration,
    UsersConfiguration,
    UsersProfilesAdminDraft,
    UsersProfilesAdministrationService,
    UsersProfilesConfiguration,
    add_pending_user,
    default_users_profiles_configuration,
    delete_functional_profile,
    save_functional_profile,
    update_administrator_colors,
    update_managed_user,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationSourceError,
    UsersConfigurationValidationError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord


def _snapshot(release_id: str = 'release-1', token: str = 'etag-1') -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', 'abc123'),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


def _configuration() -> UsersProfilesConfiguration:
    administrator = ProfileDefinition(
        key='administrator',
        label='Administrador',
        background_color='#673AB7',
        text_color='#FFFFFF',
    )
    operator = ProfileDefinition(
        key='operator',
        label='Operador',
        background_color='#123456',
        text_color='#FFFFFF',
    )
    user = UserConfiguration.create(
        issuer='entra',
        subject_id='subject-1',
        display_name='User One',
        email='one@example.com',
        profile_key='operator',
        enabled=False,
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(users=(user,)),
        profiles=ProfilesConfiguration(profiles=(administrator, operator)),
    )


def test_default_admin_configuration_contains_only_explicit_administrator_profile() -> None:
    configuration = default_users_profiles_configuration()

    assert configuration.users.users == ()
    assert tuple(profile.key for profile in configuration.profiles.profiles) == ('administrator',)


def test_admin_draft_round_trip_preserves_exact_source_snapshot() -> None:
    draft = UsersProfilesAdminDraft.create(
        owner_subject_id='subject-admin',
        configuration=_configuration(),
        source_snapshot=_snapshot(),
        saved_at_utc=datetime(2026, 9, 14, 12, 5, tzinfo=UTC),
    )

    restored = UsersProfilesAdminDraft.from_document(draft.to_document())

    assert restored == draft
    assert restored.source_snapshot.current is not None
    assert restored.source_snapshot.current.release_ref.release_id.value == 'release-1'
    assert restored.source_snapshot.concurrency_token == ConcurrencyToken('etag-1')


@pytest.mark.parametrize('schema_version', [1, 2])
def test_admin_draft_does_not_accept_legacy_browser_schema(schema_version: int) -> None:
    with pytest.raises(UsersConfigurationValidationError):
        UsersProfilesAdminDraft.from_document(
            {
                'schema_version': schema_version,
                'owner_subject_id': 'subject-admin',
                'revision': 'legacy',
                'saved_at': datetime(2026, 9, 14, 12, 5, tzinfo=UTC).isoformat(),
                'base_source_revision': 'legacy-source',
                'payload': {},
            }
        )


def test_administrator_edit_preserves_explicit_identity_and_users() -> None:
    configuration = _configuration()

    updated = update_administrator_colors(
        configuration,
        background_color='#112233',
        text_color='#AABBCC',
    )

    administrator = updated.profiles.catalog().require('administrator')
    assert administrator.key == 'administrator'
    assert administrator.label == 'Administrador'
    assert administrator.background_color == '#112233'
    assert administrator.text_color == '#AABBCC'
    assert updated.users == configuration.users


def test_functional_profile_edit_keeps_key_stable() -> None:
    configuration = _configuration()

    updated = save_functional_profile(
        configuration,
        original_key='operator',
        label='Operador Senior',
        background_color='#654321',
        text_color='#FFFFFF',
    )

    profile = updated.profiles.catalog().require('operator')
    assert profile.key == 'operator'
    assert profile.label == 'Operador Senior'
    assert updated.users.users[0].profile_key == 'operator'


def test_new_functional_profile_gets_stable_generated_key() -> None:
    configuration = default_users_profiles_configuration()

    updated = save_functional_profile(
        configuration,
        original_key=None,
        label='Supervisor Mina',
        background_color='#123456',
        text_color='#FFFFFF',
    )

    assert updated.profiles.catalog().require('supervisor_mina').label == 'Supervisor Mina'


def test_delete_referenced_profile_requires_atomic_reassignment_even_for_disabled_user() -> None:
    configuration = _configuration()

    with pytest.raises(
        UsersConfigurationValidationError,
        match='Referenced profile requires reassignment before deletion',
    ):
        delete_functional_profile(configuration, 'operator')

    updated = delete_functional_profile(
        configuration,
        'operator',
        replacement_profile_key='administrator',
    )

    assert tuple(profile.key for profile in updated.profiles.profiles) == ('administrator',)
    assert updated.users.users[0].profile_key == 'administrator'
    assert updated.users.users[0].enabled is False


def test_managed_user_creation_requires_pending_identity() -> None:
    configuration = default_users_profiles_configuration()
    pending = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-2'),
        issuer='entra',
        subject_id='subject-2',
        display_name='Pending Two',
        email='two@example.com',
    )

    updated = add_pending_user(
        configuration,
        pending,
        display_name='User Two',
        email='two@example.com',
        profile_key='administrator',
    )

    assert len(updated.users.users) == 1
    assert updated.users.users[0].issuer == pending.issuer
    assert updated.users.users[0].subject_id == pending.subject_id


def test_managed_user_update_preserves_authenticated_identity() -> None:
    configuration = _configuration()
    current = configuration.users.users[0]
    changed = UserConfiguration.create(
        user_id=current.user_id,
        issuer=current.issuer,
        subject_id=current.subject_id,
        display_name='Renamed User',
        email=current.email,
        profile_key='administrator',
        enabled=True,
    )

    updated = update_managed_user(configuration, changed)

    assert updated.users.users[0].display_name == 'Renamed User'
    assert updated.users.users[0].profile_key == 'administrator'
    assert updated.users.users[0].issuer == current.issuer
    assert updated.users.users[0].subject_id == current.subject_id


def test_administrator_profile_cannot_be_deleted() -> None:
    with pytest.raises(
        UsersConfigurationValidationError,
        match='Administrator profile cannot be deleted',
    ):
        delete_functional_profile(_configuration(), 'administrator')


class _PendingReader:
    def __init__(self, users: tuple[PendingUserRecord, ...] = ()) -> None:
        self._users = users

    def list_pending(self) -> tuple[PendingUserRecord, ...]:
        return self._users


class _Payload:
    def __init__(self, configuration: UsersProfilesConfiguration) -> None:
        self._configuration = configuration

    def projection_payload(self) -> UsersProfilesConfiguration:
        return self._configuration


class _Release:
    def __init__(self, configuration: UsersProfilesConfiguration) -> None:
        self.payload = _Payload(configuration)


class _Source:
    def __init__(self, snapshot: SourceSnapshot) -> None:
        self.source_key = snapshot.source_key
        self.snapshot = snapshot
        self.published = None
        self.configuration = _configuration()

    def get_current(self) -> SourceSnapshot:
        return self.snapshot

    def load_release(self, release_ref: SourceReleaseRef) -> _Release:
        assert self.snapshot.current is not None
        assert release_ref == self.snapshot.current.release_ref
        return _Release(self.configuration)

    def publish_configuration(self, configuration, profiles, **kwargs):
        self.published = (configuration, profiles, kwargs)
        assert self.snapshot.current is not None
        release = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.snapshot.source_key,
            release_ref=self.snapshot.current.release_ref,
            content_hash=self.snapshot.current.content_hash,
            resources=(),
        )
        return PublishResult(release=release, snapshot=self.snapshot)


def test_admin_service_publishes_with_exact_snapshot_token_and_basis_release() -> None:
    snapshot = _snapshot()
    source = _Source(snapshot)
    service = UsersProfilesAdministrationService(
        source=source,
        pending=_PendingReader(),
    )

    result = service.publish(
        _configuration(),
        expected_source_snapshot=snapshot,
        published_by='administrator',
    )

    assert result.snapshot == snapshot
    assert source.published is not None
    _, _, metadata = source.published
    assert metadata['expected_concurrency_token'] == snapshot.concurrency_token
    assert metadata['basis_release'] == snapshot.current.release_ref
    assert metadata['published_by'] == 'administrator'


def test_admin_service_rejects_stale_source_snapshot_before_publication() -> None:
    source = _Source(_snapshot('release-2', 'etag-2'))
    service = UsersProfilesAdministrationService(
        source=source,
        pending=_PendingReader(),
    )

    with pytest.raises(UsersConfigurationSourceError, match='changed before publication'):
        service.publish(
            _configuration(),
            expected_source_snapshot=_snapshot(),
            published_by='administrator',
        )

    assert source.published is None


def test_pending_filter_uses_exact_identity_against_composed_users() -> None:
    configured = _configuration()
    matching = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
    )
    different_issuer = PendingUserRecord(
        user_id=build_user_key(issuer='ENTRA', subject_id='subject-1'),
        issuer='ENTRA',
        subject_id='subject-1',
    )
    service = UsersProfilesAdministrationService(
        source=_Source(_snapshot()),
        pending=_PendingReader((matching, different_issuer)),
    )

    assert service.list_pending(configured) == (different_issuer,)
