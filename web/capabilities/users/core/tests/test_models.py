import pytest

from atlanticus.web.profiles.models import BASIC_PROFILE, LOCAL_PROFILE, ROOT_PROFILE
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    ManagedUser,
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
    build_avatar_text,
    build_runtime_user,
)


def _identity(subject_id: str = 'subject-1') -> UserIdentity:
    issuer = 'https://issuer.example'
    return UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject_id),
        issuer=issuer,
        subject_id=subject_id,
        display_name='Ada User',
        email='ADA.USER@example.com',
    )


def test_identity_is_global_identity_only_and_round_trips():
    value = _identity()
    assert value.email == 'ada.user@example.com'
    assert set(value.to_document()) == {
        'user_id',
        'issuer',
        'subject_id',
        'display_name',
        'email',
    }
    assert UserIdentity.from_document(value.to_document()) == value


def test_tool_membership_owns_profile_and_enabled_and_root_is_assignable():
    user = _identity()
    membership = ToolUserMembership(user_id=user.user_id, profile_key='ROOT', enabled=False)
    assert membership.profile_key == 'root'
    assert not membership.enabled
    assert ToolUserMembership.from_document(membership.to_document()) == membership


@pytest.mark.parametrize('profile_key', ['guest', 'local'])
def test_tool_membership_rejects_non_assignable_profiles(profile_key):
    with pytest.raises(UsersDefinitionError):
        ToolUserMembership(user_id=_identity().user_id, profile_key=profile_key)


def test_runtime_user_materializes_profile_and_operational_and_round_trips():
    identity = _identity()
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='basic')
    operational = RuntimeOperational(
        area=RuntimeOperationalReference(id='area-1', label='Area 1'),
        position=RuntimeOperationalReference(id='position-1', label='Operator'),
        group=RuntimeOperationalReference(id=5, label='Group 5'),
    )
    runtime = build_runtime_user(
        identity=identity,
        membership=membership,
        profile=BASIC_PROFILE,
        operational=operational,
    )
    assert runtime.profile == RuntimeProfile.from_profile(BASIC_PROFILE)
    assert not runtime.is_local
    assert runtime.operational == operational
    assert RuntimeUser.from_document(runtime.to_document()) == runtime


def test_runtime_user_full_access_is_derived_from_materialized_profile():
    identity = _identity()
    runtime = build_runtime_user(
        identity=identity,
        membership=ToolUserMembership(user_id=identity.user_id, profile_key='root'),
        profile=ROOT_PROFILE,
    )
    assert runtime.has_full_access


def test_runtime_user_local_state_is_derived_from_materialized_profile():
    runtime = RuntimeUser(
        identity=_identity(),
        enabled=True,
        profile=RuntimeProfile.from_profile(LOCAL_PROFILE),
    )
    assert runtime.is_local


def test_managed_user_is_identity_plus_tool_membership_without_profile_presentation():
    identity = _identity()
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='basic')
    managed = ManagedUser(identity=identity, membership=membership)
    document = managed.to_document()
    assert document['profile_key'] == 'basic'
    assert document['enabled'] is True
    assert 'avatar_background_color' not in document
    assert 'avatar_text_color' not in document


def test_registry_and_membership_snapshots_enforce_unique_user_ids():
    identity = _identity()
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='basic')
    with pytest.raises(UsersDefinitionError):
        UsersRegistrySnapshot(users=(identity, identity))
    with pytest.raises(UsersDefinitionError):
        ToolMembershipSnapshot(memberships=(membership, membership))


def test_runtime_profile_must_match_membership():
    identity = _identity()
    with pytest.raises(UsersDefinitionError):
        build_runtime_user(
            identity=identity,
            membership=ToolUserMembership(user_id=identity.user_id, profile_key='root'),
            profile=BASIC_PROFILE,
        )


def test_avatar_text_is_derived_from_display_name_not_persisted_colors():
    assert build_avatar_text('Jane Doe') == 'JD'
    assert build_avatar_text('Operator') == 'OP'
