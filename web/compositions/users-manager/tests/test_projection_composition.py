from atlanticus.web.compositions.users_manager import compose_users_projection_manager
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.users.recovery import UsersApprovedRecoveryService


def test_users_projection_registers_a_separate_authorized_manager_entry():
    service = object.__new__(UsersApprovedRecoveryService)
    principal = ManagerPrincipal('operator', 'Operator', access_keys=('users.manage',))
    entry = compose_users_projection_manager(
        recovery=service,
        snapshot_ids=lambda: (),
        principal_provider=lambda: principal,
        group_key='administration',
        access_key='users.manage',
    )
    assert entry.key == 'users-projection'
    assert entry.route == '/users-projection'
    assert entry.title == 'Proyección de usuarios'
    assert entry.group_key == 'administration'
    assert entry.access_key == 'users.manage'
    assert entry.web_module is not None
    assert entry.web_module.register_callbacks is not None
