from atlanticus.web.compositions.users_manager import (
    USERS_ADMINISTRATION_SERVICE,
    compose_users_manager,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.models import ToolMembershipSnapshot, UsersRegistrySnapshot
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore


class Registry(UsersRegistryStore):
    def load(self):
        return UsersRegistrySnapshot()

    def replace(self, users, *, expected_version):
        return UsersRegistrySnapshot(users=users, version='v1')


class Memberships(ToolMembershipStore):
    def load(self):
        return ToolMembershipSnapshot()

    def replace(self, memberships, *, expected_version):
        return ToolMembershipSnapshot(memberships=memberships, version='v1')


def test_users_manager_composition_registers_existing_administration_service() -> None:
    administration = UsersAdministrationService(
        registry=Registry(),
        memberships=Memberships(),
        profiles=lambda: ProfileCatalog(),
    )
    principal = ManagerPrincipal(
        'admin',
        'Admin',
        access_keys=('users.manage',),
    )
    composition = compose_users_manager(
        administration=administration,
        principal_provider=lambda: principal,
        group_key='administration',
        access_key='users.manage',
    )

    assert composition.entry.key == 'users'
    assert composition.entry.route == '/users'
    assert composition.entry.access_key == 'users.manage'
    assert composition.entry.web_module is not None

    services = ServiceRegistry()
    composition.entry.web_module.register_services(services)
    assert services.require(USERS_ADMINISTRATION_SERVICE) is administration
