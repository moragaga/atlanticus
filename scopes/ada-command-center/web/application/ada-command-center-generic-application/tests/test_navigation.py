from ada_command_center.web.application.generic.navigation import navigation_principal
from atlanticus.web.manager import ManagerPrincipal


def test_local_manager_principal_becomes_navigation_administrator() -> None:
    principal = navigation_principal(
        ManagerPrincipal(
            subject_id='local:test',
            display_name='Local Operator',
            profile_keys=('local',),
            administrative_override=True,
            is_local=True,
        )
    )

    assert principal.access_key == 'local'
    assert principal.administrative_override is True
    assert principal.user.display_name == 'Local Operator'
    assert principal.user.profile_key == 'local'
    assert principal.user.avatar_text == 'LO'
