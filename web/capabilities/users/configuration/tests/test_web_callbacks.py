from datetime import UTC, datetime

import pytest

pytest.importorskip('dash')

from atlanticus.web.source.models import SourceKey, SourceSnapshot
from atlanticus.web.users.configuration import (
    UsersProfilesAdminDraft,
    UsersProfilesAdministrationService,
    UsersProfilesConfiguration,
    default_users_profiles_configuration,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.web.canonical_callbacks import (
    _draft,
    _save_profile,
    _save_user,
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord


class _Source:
    def __init__(self) -> None:
        self.source_key = SourceKey('users')
        self.snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=None,
            concurrency_token=None,
        )

    def get_current(self) -> SourceSnapshot:
        return self.snapshot

    def load_release(self, _release_ref):
        raise AssertionError('A source without current release must not be loaded')


class _PendingReader:
    def __init__(self, users: tuple[PendingUserRecord, ...] = ()) -> None:
        self._users = users

    def list_pending(self) -> tuple[PendingUserRecord, ...]:
        return self._users


def _context(
    pending: tuple[PendingUserRecord, ...] = (),
) -> UsersAdminWebContext:
    administration = UsersProfilesAdministrationService(
        source=_Source(),
        pending=_PendingReader(pending),
    )
    return UsersAdminWebContext(
        administration=administration,
        draft_store_id='draft',
        saved_draft_store_id='saved-draft',
        draft_save_action_id='workflow-save-draft',
        workflow_refresh_signal_id='workflow-refresh',
        editor_revision_store_id='editor-revision',
        draft_owner_provider=lambda: 'tester',
    )


def test_profile_editor_generates_stable_key_inside_canonical_profiles() -> None:
    updated = _save_profile(
        default_users_profiles_configuration(),
        {'mode': 'create'},
        'Operador Planta',
        '#C9A24B',
        '#071522',
    )

    assert updated.profile_catalog().require('administrator').key == 'administrator'
    operator = updated.profile_catalog().require('operador_planta')
    assert operator.label == 'Operador Planta'
    assert operator.background_color == '#C9A24B'
    assert operator.text_color == '#071522'


def test_pending_user_keeps_identity_when_added_to_canonical_draft() -> None:
    pending = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Usuario Pendiente',
        email='pending@example.com',
    )
    context = _context((pending,))
    configuration = default_users_profiles_configuration()

    updated = _save_user(
        context,
        configuration,
        {
            'mode': 'pending',
            'user_id': pending.user_id,
            'issuer': pending.issuer,
            'subject_id': pending.subject_id,
        },
        display_name='Usuario Pendiente',
        email='pending@example.com',
        profile_key='administrator',
        enabled=True,
    )

    user = updated.users.users[0]
    assert user.user_id == pending.user_id
    assert user.issuer == pending.issuer
    assert user.subject_id == pending.subject_id
    assert user.profile_key == 'administrator'


def test_legacy_browser_draft_is_rejected_instead_of_migrated() -> None:
    legacy = {
        'schema_version': 1,
        'owner_subject_id': 'tester',
        'revision': 'legacy',
        'saved_at': datetime(2026, 9, 15, tzinfo=UTC).isoformat(),
        'base_source_revision': 'source-legacy',
        'payload': {},
    }

    with pytest.raises(UsersConfigurationValidationError):
        _draft(legacy, owner_subject_id='tester')


def test_schema_2_draft_preserves_exact_snapshot_and_owner() -> None:
    configuration = default_users_profiles_configuration()
    snapshot = SourceSnapshot(
        source_key=SourceKey('users'),
        current=None,
        concurrency_token=None,
    )
    draft = UsersProfilesAdminDraft.create(
        owner_subject_id='tester',
        configuration=configuration,
        source_snapshot=snapshot,
        saved_at_utc=datetime(2026, 9, 15, tzinfo=UTC),
    )

    restored = _draft(draft.to_document(), owner_subject_id='tester')

    assert restored == draft
    assert isinstance(restored.configuration, UsersProfilesConfiguration)
    assert restored.source_snapshot == snapshot
