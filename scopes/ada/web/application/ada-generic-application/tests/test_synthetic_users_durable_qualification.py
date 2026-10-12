from __future__ import annotations

import os
from dataclasses import dataclass, replace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from flask import Flask

from ada.web.access.configuration import (
    ADA_ACCESS_SOURCE_KEY,
    AdaAccessConfiguration,
    AdaAccessSourceService,
    create_ada_access_projection_service,
)
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.generic.manager.deployment import (
    open_durable_manager,
    prepare_durable_manager_resources,
)
from ada.web.application.generic.manager.principal import compose_integrated_manager_dependencies
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.application.generic.users.access import AdaInitialUsersStore
from ada.web.application.generic.users.materialization import AdaUsersRuntimeMaterializer
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
from atlanticus.web.users.models import DiscoveredUser, ToolUserMembership, UserIdentity
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersDirectoryReader

_SUBJECTS = (
    ('synthetic-admin', 'Synthetic Administrator'),
    ('synthetic-operator', 'Synthetic Operator'),
    ('synthetic-supervisor', 'Synthetic Supervisor'),
    ('synthetic-disabled', 'Synthetic Disabled'),
)


@dataclass(frozen=True, slots=True)
class _Person:
    issuer: str
    subject_id: str
    display_name: str

    @property
    def user_id(self) -> str:
        return build_user_key(issuer=self.issuer, subject_id=self.subject_id)

    def identity(self) -> UserIdentity:
        return UserIdentity(
            user_id=self.user_id,
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )

    def discovered(self) -> DiscoveredUser:
        return DiscoveredUser(
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )

    def authenticated(self) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            provider_key='synthetic',
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=f'{self.subject_id}@example.invalid',
        )


class _Directory(UsersDirectoryReader):
    def __init__(self, people: dict[str, _Person]) -> None:
        self._people = people

    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        return tuple(person.discovered() for person in self._people.values())


class _IdentityProvider(IdentityProvider):
    def __init__(self, person: _Person) -> None:
        self._person = person

    @property
    def key(self) -> str:
        return 'synthetic'

    @property
    def production_ready(self) -> bool:
        return False

    def validate_configuration(self) -> None:
        if os.getenv('ATLANTICUS_ENVIRONMENT') != 'local' or os.getenv('ADA_UR05B_RUN') != '1':
            raise RuntimeError('Synthetic durable identity is unavailable outside local qualification')

    def resolve(self, request) -> AuthenticatedIdentity:
        del request
        self.validate_configuration()
        return self._person.authenticated()


def _local_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == 'http'
            and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
            and parsed.port is not None
        )
    except ValueError:
        return False


def _settings() -> AdaGenericSettings:
    if os.getenv('ATLANTICUS_ENVIRONMENT') != 'local':
        raise RuntimeError('Durable qualification requires a local environment')
    if os.getenv('ADA_UR05B_RUN') != '1':
        raise RuntimeError('Durable qualification requires explicit opt-in')

    storage = os.environ['UR05B_STORAGE_CONNECTION_STRING']
    cosmos_endpoint = os.environ['UR05B_COSMOS_ENDPOINT']
    cosmos_key = os.environ['UR05B_COSMOS_KEY']
    database = os.environ['UR05B_COSMOS_DATABASE']
    if not cosmos_key or not _local_url(cosmos_endpoint):
        raise RuntimeError('Cosmos qualification must target a loopback HTTP emulator')
    if not database.startswith('ur05b-') or len(database) < 7:
        raise RuntimeError('Cosmos qualification database must have an ur05b- prefix')
    if not (
        storage == 'UseDevelopmentStorage=true'
        or any(
            part.startswith('BlobEndpoint=') and _local_url(part.partition('=')[2])
            for part in storage.split(';')
        )
    ):
        raise RuntimeError('Blob qualification must target a loopback emulator')

    run_id = uuid4().hex[:16]
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_APPLICATION_NAMESPACE': f'ur05b-{run_id}',
            'ADA_TOOL_NAMESPACE': 'synthetic',
            'ADA_STORAGE_CONTAINER_NAME': 'ur05b-qualification',
            'ADA_STORAGE_CONNECTION_STRING': storage,
            'ADA_COSMOS_ENDPOINT': cosmos_endpoint,
            'ADA_COSMOS_KEY': cosmos_key,
            'ADA_COSMOS_DATABASE_NAME': database,
        }
    )


def _seed_configuration(stores) -> None:
    profiles_source = ProfilesSourceService(
        source=stores.profiles_source, source_key=PROFILES_CONFIGURATION_SOURCE_KEY
    )
    profiles_source.publish_configuration(
        ProfilesConfiguration(),
        published_by='ur05b-qualification',
        expected_concurrency_token=None,
        basis_release=None,
    )
    profiles_projection = create_profiles_projection_service(
        source=stores.profiles_source, projection=stores.profiles
    )
    profiles_target = profiles_projection.select_current_target(PROFILES_CONFIGURATION_SOURCE_KEY)
    assert profiles_target is not None
    profiles_projection.project(profiles_target)

    access_source = AdaAccessSourceService(source=stores.access_source, source_key=ADA_ACCESS_SOURCE_KEY)
    access_source.publish_configuration(
        AdaAccessConfiguration(
            access_keys=('dashboard.view', 'reports.read'),
            profile_access=(
                ProfileAccessGrant(profile_key='basic', access_keys=('dashboard.view',)),
            ),
        ),
        published_by='ur05b-qualification',
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


def _operations(stores) -> OperationalIdentificationService:
    service = OperationalIdentificationService(
        source_store=stores.operational_source,
        projections=stores.operational,
        memberships=stores.users_memberships,
    )
    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog(positions=(Position(id='operator', label='Operator'),)),
        actor='ur05b-qualification',
        expected=snapshot,
    )
    assert service.project_current(CATALOG_SOURCE_KEY) is not None
    return service


def _promote(administration, stores, person: _Person) -> None:
    administration.promote(
        person.user_id,
        profile_key='basic',
        expected_registry_version=stores.users_registry.load().version,
        expected_membership_version=stores.users_memberships.load().version,
    )


def test_durable_qualification_requires_explicit_local_opt_in(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.delenv('ADA_UR05B_RUN', raising=False)
    with pytest.raises(RuntimeError, match='explicit opt-in'):
        _settings()
    person = _Person('urn:atlanticus:ur05b:case', 'synthetic-operator', 'Operator')
    provider = _IdentityProvider(person)
    assert not provider.production_ready
    with pytest.raises(RuntimeError, match='outside local qualification'):
        provider.resolve(object())


def test_durable_qualification_rejects_nonlocal_endpoints(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ADA_UR05B_RUN', '1')
    monkeypatch.setenv('UR05B_STORAGE_CONNECTION_STRING', 'UseDevelopmentStorage=true')
    monkeypatch.setenv('UR05B_COSMOS_KEY', 'test-only')
    monkeypatch.setenv('UR05B_COSMOS_DATABASE', 'ur05b-test-isolated')
    monkeypatch.setenv('UR05B_COSMOS_ENDPOINT', 'https://example.com:8081')
    with pytest.raises(RuntimeError, match='loopback HTTP emulator'):
        _settings()
    monkeypatch.setenv('UR05B_COSMOS_ENDPOINT', 'http://127.0.0.1:8081')
    monkeypatch.setenv('UR05B_STORAGE_CONNECTION_STRING', 'BlobEndpoint=https://example.com:10000')
    with pytest.raises(RuntimeError, match='Blob qualification must target'):
        _settings()


@pytest.mark.skipif(
    os.getenv('ADA_UR05B_RUN') != '1',
    reason='Requires explicitly configured, isolated Blob and Cosmos local emulators',
)
def test_synthetic_users_with_real_blob_and_cosmos(monkeypatch):
    settings = _settings()
    run_issuer = f'urn:atlanticus:ur05b:{settings.application_namespace}'
    people = {
        subject: _Person(run_issuer, subject, name)
        for subject, name in _SUBJECTS
    }
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')

    with open_durable_manager(settings) as deployment:
        preparation = prepare_durable_manager_resources(
            deployment, action='prepare', environment=settings.environment
        )
        assert preparation.status == 'COMPLETED', preparation.to_dict()
        stores = replace(deployment.stores, users_directory=_Directory(people))
        assert stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY) is None, (
            'Durable qualification requires a fresh Cosmos database'
        )
        assert stores.access.get_active(ADA_ACCESS_SOURCE_KEY) is None
        assert stores.operational.get_active(CATALOG_SOURCE_KEY) is None
        assert stores.users_registry.load().users == ()
        assert stores.users_memberships.load().memberships == ()
        _seed_configuration(stores)
        operations = _operations(stores)

        admin_person = people['synthetic-admin']
        disabled = people['synthetic-disabled']
        operator = people['synthetic-operator']
        supervisor = people['synthetic-supervisor']
        stores.users_registry.replace(
            (admin_person.identity(), disabled.identity()), expected_version=None
        )
        stores.users_memberships.replace(
            (
                ToolUserMembership(user_id=admin_person.user_id, profile_key='root'),
                ToolUserMembership(user_id=disabled.user_id, profile_key='basic', enabled=False),
            ),
            expected_version=None,
        )
        materializer = AdaUsersRuntimeMaterializer(stores=stores)
        for person in (admin_person, disabled):
            materializer.publish_user(person.user_id, writer=stores.users_runtime_writer)

        dependencies = compose_integrated_manager_dependencies(
            stores=stores,
            access_runtime=AccessRuntime(),
            users_runtime=UsersRuntime(),
            trusted_local_users=False,
        )
        services = ServiceRegistry()
        dependencies.users_entry.web_module.register_services(services)
        administration = services.require(USERS_ADMINISTRATION_SERVICE)
        _promote(administration, stores, operator)
        _promote(administration, stores, supervisor)
        before_supervisor = stores.users_runtime.resolve(supervisor.authenticated())
        before_admin = stores.users_runtime.resolve(admin_person.authenticated())
        original_operator = stores.users_runtime.resolve(operator.authenticated())
        assert original_operator is not None
        assert original_operator.operational.position is None

        runtime = UsersRuntime()
        resolver = UsersAccessResolver(
            store=AdaInitialUsersStore(
                runtime=stores.users_runtime,
                profiles=stores.profiles,
                access=stores.access,
            ),
            runtime=runtime,
        )
        flask = Flask(__name__)
        flask.secret_key = 'ur05b-test-only'
        with flask.test_request_context('/manager'):
            original_decision = resolver.resolve(operator.authenticated(), load_id='load-1')
            assert original_decision.status is AccessStatus.READY
            original_access = AccessSnapshot.resolved(
                load_id='load-1', identity=operator.authenticated(), decision=original_decision
            )
            assert runtime.current(original_access).operational.position is None

        snapshot, _ = operations.assignment_for_edit(operator.user_id)
        operations.publish_assignment(
            OperationalAssignment(
                user_id=operator.user_id,
                area_id='mina',
                position_id='operator',
                group_id=2,
            ),
            actor='ur05b-qualification',
            expected=snapshot,
        )
        saved_snapshot, _ = operations.assignment_for_edit(operator.user_id)
        assert stores.users_runtime.resolve(operator.authenticated()) == original_operator
        assert dependencies.operational_runtime_publisher is not None
        published = dependencies.operational_runtime_publisher(operator.user_id)
        assert published.operational.area.label == 'Mina'
        assert published.operational.position.label == 'Operator'
        assert published.operational.group.label == 'Grupo 2'
        assert operations.assignment_for_edit(operator.user_id)[0] == saved_snapshot
        assert stores.users_runtime.resolve(admin_person.authenticated()) == before_admin
        assert stores.users_runtime.resolve(supervisor.authenticated()) == before_supervisor

        provider = _IdentityProvider(operator)
        provider.validate_configuration()
        assert provider.production_ready is False
        assert provider.resolve(object()) == operator.authenticated()
        with flask.test_request_context('/manager'):
            decision = resolver.resolve(operator.authenticated(), load_id='load-2')
            assert decision.status is AccessStatus.READY
            access = AccessSnapshot.resolved(
                load_id='load-2', identity=operator.authenticated(), decision=decision
            )
            assert runtime.current(access).operational == published.operational
            disabled_decision = resolver.resolve(disabled.authenticated(), load_id='load-3')
            assert disabled_decision.status is AccessStatus.USER_DISABLED

        administration.update(
            operator.user_id,
            profile_key='root',
            enabled=False,
            expected_membership_version=stores.users_memberships.load().version,
        )
        assert stores.users_runtime.resolve(operator.authenticated()).enabled is False
        assert stores.users_runtime.resolve(operator.authenticated()).profile.id == 'root'
        assert stores.users_runtime.resolve(supervisor.authenticated()) == before_supervisor

    with open_durable_manager(settings) as reopened:
        stores = reopened.stores
        persisted = stores.users_runtime.resolve(operator.authenticated())
        assert persisted is not None
        assert persisted.enabled is False
        assert persisted.profile.id == 'root'
        assert persisted.operational.position.label == 'Operator'
        assert stores.users_registry.load().get(operator.user_id) == operator.identity()
        assert stores.users_memberships.load().get(operator.user_id).enabled is False
        operations = OperationalIdentificationService(
            source_store=stores.operational_source,
            projections=stores.operational,
            memberships=stores.users_memberships,
        )
        assert operations.assignment_for_read(operator.user_id).position_id == 'operator'
        assert operations.assignment_for_edit(operator.user_id)[0] == saved_snapshot
        assert stores.users_runtime.resolve(supervisor.authenticated()) == before_supervisor

