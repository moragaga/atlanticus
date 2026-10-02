from __future__ import annotations

import pytest

from ada.web.application.generic.navigation_binding import (
    manager_navigation_principal,
    public_navigation_principal,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY
from atlanticus.web.users.local import LOCAL_USERS


@pytest.mark.parametrize('local_user', LOCAL_USERS, ids=('jane', 'john'))
def test_known_local_navigation_preserves_the_users_avatar_palette(local_user) -> None:
    principal = ManagerPrincipal(
        subject_id=local_user.subject_id,
        display_name=local_user.display_name,
        profile_keys=(LOCAL_PROFILE_KEY,),
        is_local=True,
    )
    result = manager_navigation_principal(principal, allow_local=True)

    assert result.user.display_name == local_user.display_name
    assert result.user.avatar_background_color == local_user.avatar_background_color
    assert result.user.avatar_text_color == local_user.avatar_text_color
    assert result.user.profile_background_color == local_user.avatar_background_color
    assert result.user.profile_text_color == local_user.avatar_text_color
    assert result.administrative_override is True


@pytest.mark.parametrize('local_user', LOCAL_USERS, ids=('jane', 'john'))
def test_local_avatar_is_resolved_from_subject_not_display_name(local_user) -> None:
    principal = ManagerPrincipal(
        subject_id=local_user.subject_id,
        display_name='Visible Alias',
        profile_keys=(LOCAL_PROFILE_KEY,),
        is_local=True,
    )
    result = manager_navigation_principal(principal)

    assert result.user.avatar_background_color == local_user.avatar_background_color
    assert result.user.profile_background_color == local_user.avatar_background_color
    assert result.user.avatar_text == 'VA'
    assert result.administrative_override is False


@pytest.mark.parametrize('local_user', LOCAL_USERS, ids=('jane', 'john'))
def test_managed_identity_cannot_inherit_a_local_avatar_by_subject_only(local_user) -> None:
    principal = ManagerPrincipal(
        subject_id=local_user.subject_id,
        display_name='Managed User',
        profile_keys=('basic',),
        is_local=False,
    )
    result = manager_navigation_principal(principal)

    assert result.user.avatar_background_color == result.user.profile_background_color
    assert result.user.avatar_text_color == result.user.profile_text_color
    assert result.administrative_override is False


def test_unknown_local_subject_keeps_the_existing_fallback() -> None:
    principal = ManagerPrincipal(
        subject_id='local:unknown',
        display_name='Unknown Local',
        profile_keys=(LOCAL_PROFILE_KEY,),
        is_local=True,
    )
    result = manager_navigation_principal(principal, allow_local=True)

    assert result.user.avatar_background_color == result.user.profile_background_color
    assert result.user.avatar_text_color == result.user.profile_text_color
    assert result.administrative_override is True


def test_public_navigation_is_unchanged() -> None:
    result = public_navigation_principal()
    assert result.user.display_name == 'Visitante'
    assert result.user.avatar_background_color == result.user.profile_background_color
    assert result.administrative_override is False
