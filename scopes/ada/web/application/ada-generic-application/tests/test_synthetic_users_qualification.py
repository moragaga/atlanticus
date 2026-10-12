from __future__ import annotations

import os
from dataclasses import dataclass, replace

import pytest
from flask import Flask

from ada.web.access.configuration import (
    ADA_ACCESS_SOURCE_KEY,
    AdaAccessConfiguration,
    AdaAccessSourceService,
    create_ada_access_projection_service,
)
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.configuration_manager.local_runtime import (
    InProcessUsersRuntimeStore,
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.users_publication import (
    AdaUsersAdministrationService,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.manager.principal import compose_integrated_manager_dependencies
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.application.generic.users.access import AdaInitialUsersStore
from ada.web.application.generic.users.materialization import AdaUsersRuntimeMaterializer
from ada.web.application.generic.users.publication import AdaLocalRuntimeUserWriter
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
)
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.compositions.users_manager import USERS_ADMINISTRATION_SERVICE
from atlanticus.web.identity.access import AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.profiles.configuration import (
    ProfilesConfiguration,
    ProfilesSourceService,
    create_profiles_projection_service,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    DiscoveredUser,
    ToolUserMembership,
    UserIdentity,
)
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersDirectoryReader

_ISSUER = 'urn:atlanticus:synthetic-qualification'
_SUBJECTS = (
    ('synthetic-admin', 'Synthetic Administrator'),
    ('synthetic-operator', 'Synthetic Operator'),
    ('synthetic-supervisor', 'Synthetic Supervisor'),
    ('synthetic-disabled', 'Synthetic Disabled'),
)


@dataclass(frozen=True, slots=True)
class SyntheticPerson:
    subject_id: str
    display_name: str

    @property
    def user_id(self) -> str:
        return build_user_key(issuer=_ISSUER, subject_id=self.subject_id)

    def identity(self) -> UserIdentity:
        return UserIdentity(
            user_id=self.user_id,
            issuer=_ISSUER,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )

    def discovered(self) -> DiscoveredUser:
        return DiscoveredUser(
            issuer=_ISSUER,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )

    def authenticated(self) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            provider_key='synthetic',
            issuer=_ISSUER,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )


_PEOPLE = {subject: SyntheticPerson(subject, label) for subject, label in _SUBJECTS}


class SyntheticDirectory(UsersDirectoryReader):
    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        _require_qualification()
        return tuple(person.discovered() for person in _PEOPLE.values())


class SyntheticIdentityProvider(IdentityProvider):
    def __init__(self, subject_id: str) -> None:
        if subject_id not in _PEOPLE:
            raise ValueError('Unknown synthetic qualification subject')
        self._person = _PEOPLE[subject_id]

    @property
    def key(self) -> str:
        return 'synthetic'

    @property
    def production_ready(self) -> bool:
        return False

    def validate_configuration(self) -> None:
        _require_qualification()

    def resolve(self, request) -> AuthenticatedIdentity:
        del request
        self.validate_configuration()
        return self._person.authenticated()


def _require_qualification() -> None:
    if (
        os.environ.get('ATLANTICUS_ENVIRONMENT') != 'local'
        or os.environ.get('ADA_SYNTHETIC_QUALIFICATION') != '1'
    ):
        raise RuntimeError('Synthetic identities require explicit local qualification')


def _seed_profiles_access(stores) -> None:
    profiles_source = ProfilesSourceService(
        source=stores.profiles_source,
        source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
    )
    profiles_source.publish_configuration(
        ProfilesConfiguration(),
        published_by='synthetic-qualification',
        expected_concurrency_token=None,
        basis_release=None,
    )
    profiles_projection = create_profiles_projection_service(
        source=stores.profiles_source,
        projection=stores.profiles,
    )
    profiles_target = profiles_projection.select_current_target(PROFILES_CONFIGURATION_SOURCE_KEY)
    assert profiles_target is not None
    profiles_projection.project(profiles_target)

    access_source = AdaAccessSourceService(
        source=stores.access_source,
        source_key=ADA_ACCESS_SOURCE_KEY,
    )
    access_source.publish_configuration(
        AdaAccessConfiguration(
            access_keys=('dashboard.view', 'reports.read'),
            profile_access=(
                ProfileAccessGrant(
                    profile_key='basic',
                    access_keys=('dashboard.view',),
                ),
            ),
        ),
        published_by='synthetic-qualification',
        expected_concurrency_token=None,
        basis_release=None,
    )
    access_projection = create_ada_access_projection_service(
        source=stores.access_source,
        projection=stores.access,
        profiles_projection=stores.profiles,
        profiles_source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
    )
    access_target = access_projection.select_current_target(ADA_ACCESS_SOURCE_KEY)
    assert access_target is not None
    access_projection.project(access_target)


def _seed_operational_catalog(stores) -> OperationalIdentificationService:
    service = OperationalIdentificationService(
        source_store=stores.operational_source,
        projections=stores.operational,
        memberships=stores.users_memberships,
    )
    snapshot, _catalog = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog(positions=(Position(id='operator', label='Operator'),)),
        actor='synthetic-qualification',
        expected=snapshot,
    )
    projected = service.project_current(CATALOG_SOURCE_KEY)
    assert projected is not None
    return service


def _seed_initial_users(stores) -> None:
    admin = _PEOPLE['synthetic-admin']
    disabled = _PEOPLE['synthetic-disabled']
    stores.users_registry.replace(
        (admin.identity(), disabled.identity()),
        expected_version=None,
    )
    stores.users_memberships.replace(
        (
            ToolUserMembership(user_id=admin.user_id, profile_key='root'),
            ToolUserMembership(user_id=disabled.user_id, profile_key='basic', enabled=False),
        ),
        expected_version=None,
    )
    materializer = AdaUsersRuntimeMaterializer(stores=stores)
    materializer.publish_user(admin.user_id, writer=AdaLocalRuntimeUserWriter(stores.users_runtime))
    materializer.publish_user(disabled.user_id, writer=AdaLocalRuntimeUserWriter(stores.users_runtime))


@pytest.fixture
def qualification(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ADA_SYNTHETIC_QUALIFICATION', '1')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    stores = replace(
        stores,
        users_directory=SyntheticDirectory(),
        users_runtime=InProcessUsersRuntimeStore(),
    )
    _seed_profiles_access(stores)
    _seed_initial_users(stores)
    operations = _seed_operational_catalog(stores)
    dependencies = compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=AccessRuntime(),
        users_runtime=UsersRuntime(),
        trusted_local_users=False,
    )
    services = ServiceRegistry()
    dependencies.users_entry.web_module.register_services(services)
    administration = services.require(
        USERS_ADMINISTRATION_SERVICE,
        AdaUsersAdministrationService,
    )
    return stores, operations, dependencies, administration


def _promote(administration, stores, person: SyntheticPerson) -> None:
    administration.promote(
        person.user_id,
        profile_key='basic',
        expected_registry_version=stores.users_registry.load().version,
        expected_membership_version=stores.users_memberships.load().version,
    )


def _assignment(operations, person: SyntheticPerson, *, area='mina', group=2):
    snapshot, _current = operations.assignment_for_edit(person.user_id)
    operations.publish_assignment(
        OperationalAssignment(
            user_id=person.user_id,
            area_id=area,
            position_id='operator',
            group_id=group,
        ),
        actor='synthetic-qualification',
        expected=snapshot,
    )
    return operations.assignment_for_edit(person.user_id)[0]


def _resolver(stores):
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(
        store=AdaInitialUsersStore(
            runtime=stores.users_runtime,
            profiles=stores.profiles,
            access=stores.access,
        ),
        runtime=runtime,
    )
    return resolver, runtime


def test_synthetic_users_are_fixed_not_claimed_from_http(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ADA_SYNTHETIC_QUALIFICATION', '1')
    provider = SyntheticIdentityProvider('synthetic-operator')
    assert provider.production_ready is False
    assert provider.resolve(object()) == _PEOPLE['synthetic-operator'].authenticated()
    assert len({user.user_id for user in _PEOPLE.values()}) == 4
    assert {item.subject_id for item in SyntheticDirectory().list_discovered()} == set(_PEOPLE)
    with pytest.raises(ValueError, match='Unknown synthetic'):
        SyntheticIdentityProvider('untrusted-user')

    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    with pytest.raises(RuntimeError, match='explicit local qualification'):
        provider.resolve(object())
    with pytest.raises(RuntimeError, match='explicit local qualification'):
        SyntheticDirectory().list_discovered()
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.delenv('ADA_SYNTHETIC_QUALIFICATION')
    with pytest.raises(RuntimeError, match='explicit local qualification'):
        provider.validate_configuration()


def test_promote_project_publish_and_refresh_user_snapshot(qualification):
    stores, operations, dependencies, administration = qualification
    operator = _PEOPLE['synthetic-operator']
    supervisor = _PEOPLE['synthetic-supervisor']
    assert operator.user_id in {
        candidate.user_id for candidate in administration.discover().candidates
        if candidate.state.value == 'promotable'
    }
    _promote(administration, stores, operator)
    assert stores.users_runtime.resolve(operator.authenticated()).profile.id == 'basic'
    before_admin = stores.users_runtime.resolve(_PEOPLE['synthetic-admin'].authenticated())
    _promote(administration, stores, supervisor)
    before_supervisor = stores.users_runtime.resolve(supervisor.authenticated())

    resolver, runtime = _resolver(stores)
    app = Flask(__name__)
    app.secret_key = 'synthetic-session'
    with app.test_request_context('/manager'):
        decision = resolver.resolve(operator.authenticated(), load_id='load-1')
        assert decision.status is AccessStatus.READY
        access = AccessSnapshot.resolved(
            load_id='load-1', identity=operator.authenticated(), decision=decision
        )
        initial = runtime.current(access)
        assert initial.access_keys == ('dashboard.view',)
        assert initial.operational.position is None
        _assignment(operations, operator)
        assert dependencies.operational_runtime_publisher is not None
        updated = dependencies.operational_runtime_publisher(operator.user_id)
        assert updated.operational.area.label == 'Mina'
        assert updated.operational.position.label == 'Operator'
        assert updated.operational.group.label == 'Grupo 2'
        assert runtime.current(access) == initial

        refreshed_decision = resolver.resolve(operator.authenticated(), load_id='load-2')
        refreshed_access = AccessSnapshot.resolved(
            load_id='load-2', identity=operator.authenticated(), decision=refreshed_decision
        )
        refreshed = runtime.current(refreshed_access)
        assert refreshed.operational == updated.operational
        assert runtime.current_or_none(access) is None

    assert stores.users_runtime.resolve(_PEOPLE['synthetic-admin'].authenticated()) == before_admin
    assert stores.users_runtime.resolve(supervisor.authenticated()) == before_supervisor

    administration.update(
        operator.user_id,
        profile_key='root',
        enabled=False,
        expected_membership_version=stores.users_memberships.load().version,
    )
    assert not stores.users_runtime.resolve(operator.authenticated()).enabled
    assert stores.users_runtime.resolve(operator.authenticated()).profile.id == 'root'
    assert stores.users_runtime.resolve(supervisor.authenticated()).enabled


def test_assignment_without_individual_projection_updates_runtime_and_preserves_source(qualification):
    stores, operations, dependencies, administration = qualification
    operator = _PEOPLE['synthetic-operator']
    _promote(administration, stores, operator)
    existing_runtime = stores.users_runtime.resolve(operator.authenticated())
    durable_snapshot = _assignment(operations, operator)
    assert stores.users_runtime.resolve(operator.authenticated()) == existing_runtime
    assert dependencies.operational_runtime_publisher is not None
    recovered = dependencies.operational_runtime_publisher(operator.user_id)
    assert recovered.operational.position.id == 'operator'
    assert operations.assignment_for_edit(operator.user_id)[0] == durable_snapshot


def test_users_runtime_outage_retries_without_rewriting_source(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ADA_SYNTHETIC_QUALIFICATION', '1')

    class FaultyRuntime(InProcessUsersRuntimeStore):
        def __init__(self):
            super().__init__()
            self.fail = False

        def upsert_user(self, user):
            if self.fail:
                raise ConnectionError('Sensitive provider detail')
            return super().upsert_user(user)

    runtime = FaultyRuntime()
    stores = replace(
        create_local_configuration_manager_stores(source_root=tmp_path / 'source'),
        users_directory=SyntheticDirectory(),
        users_runtime=runtime,
    )
    _seed_profiles_access(stores)
    _seed_initial_users(stores)
    operations = _seed_operational_catalog(stores)
    materializer = AdaUsersRuntimeMaterializer(stores=stores)
    operator = _PEOPLE['synthetic-operator']
    admin = AdaUsersAdministrationService(
        registry=stores.users_registry,
        memberships=stores.users_memberships,
        profiles=lambda: stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY).payload,
        directory=stores.users_directory,
        publish_runtime=lambda user_id: materializer.publish_user(
            user_id, writer=AdaLocalRuntimeUserWriter(runtime)
        ),
    )
    _promote(admin, stores, operator)
    previous = runtime.resolve(operator.authenticated())
    durable_snapshot = _assignment(operations, operator)
    runtime.fail = True
    with pytest.raises(ConnectionError, match='Sensitive provider detail'):
        materializer.publish_operational(
            operator.user_id, writer=AdaLocalRuntimeUserWriter(runtime)
        )
    assert runtime.resolve(operator.authenticated()) == previous
    assert operations.assignment_for_edit(operator.user_id)[0] == durable_snapshot
    runtime.fail = False
    published = materializer.publish_operational(
        operator.user_id, writer=AdaLocalRuntimeUserWriter(runtime)
    )
    assert published.operational.position.id == 'operator'
    assert operations.assignment_for_edit(operator.user_id)[0] == durable_snapshot


def test_synthetic_bootstrap_uses_real_manager_authentication_path(qualification, tmp_path, monkeypatch):
    stores, _operations, _dependencies, _administration = qualification
    monkeypatch.chdir(tmp_path)
    settings = AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_TOOL_NAMESPACE': 'synthetic_qualification',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )
    app = bootstrap.create_operational_application_runtime(
        settings=settings,
        manager_stores=stores,
        identity_provider=SyntheticIdentityProvider('synthetic-admin'),
    )
    assert app.server.test_client().get('/manager').status_code == 200

    resolver, _users = _resolver(stores)
    flask_app = Flask(__name__)
    flask_app.secret_key = 'synthetic-session'
    with flask_app.test_request_context('/'):
        decision = resolver.resolve(
            _PEOPLE['synthetic-disabled'].authenticated(), load_id='disabled'
        )
        assert decision.status is AccessStatus.USER_DISABLED
