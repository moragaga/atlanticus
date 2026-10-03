from ada_command_center.web.application.generic.navigation import navigation_principal
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY
from atlanticus.web.users.local import LOCAL_USERS


def test_local_manager_principal_becomes_navigation_administrator() -> None:
    local_user = LOCAL_USERS[0]
    principal = navigation_principal(
        ManagerPrincipal(
            subject_id=local_user.subject_id,
            display_name=local_user.display_name,
            profile_keys=(LOCAL_PROFILE_KEY,),
            administrative_override=True,
            is_local=True,
        ),
        allow_local=True,
    )

    assert principal.access_key == 'local'
    assert principal.administrative_override is True
    assert principal.user.display_name == local_user.display_name
    assert principal.user.profile_key == 'local'
    assert principal.user.avatar_background_color == local_user.avatar_background_color
    assert principal.user.avatar_text_color == local_user.avatar_text_color


def test_managed_root_navigation_override_is_not_copied_blindly() -> None:
    principal = navigation_principal(
        ManagerPrincipal(
            subject_id='root-user',
            display_name='Root User',
            profile_keys=('root',),
            administrative_override=True,
            is_local=False,
            profile_label='Root',
            profile_background_color='#112233',
            profile_text_color='#FFFFFF',
            avatar_text='RU',
        )
    )

    assert principal.administrative_override is True
    assert principal.user.profile_label == 'Root'
    assert principal.user.profile_background_color == '#112233'
    assert principal.user.avatar_text == 'RU'
