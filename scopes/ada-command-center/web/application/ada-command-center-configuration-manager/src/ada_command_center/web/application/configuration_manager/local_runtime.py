from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Generic, TypeVar

from ada_command_center.web.alarms.configuration.resources import (
    ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME,
)
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from ada_command_center.web.alarms.persistence import (
    AlarmConfigurationPersistenceSettings,
    AlarmConfigurationProjectionProvider,
    AlarmConfigurationSourceProvider,
    compose_alarm_configuration_persistence,
)
from ada_command_center.web.application.configuration_manager.administration import (
    CommandCenterAdministrationStores,
    compose_command_center_administration,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    COMMAND_CENTER_CATALOG_BLOB_NAME,
    COMMAND_CENTER_NAMESPACE,
    STORAGE_CONTAINER_VARIABLE,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada_command_center.web.tools.catalog import BlobToolCatalogStore, BlobToolCatalogStoreSettings
from ada_command_center.web.tools.discovery_cosmos.manager import ToolCatalogManagerService
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.users.errors import UserAlreadyPromotedError, UsersRegistryConflictError
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore

PayloadT = TypeVar('PayloadT')


class InProcessProjectionStore(ProjectionStore[PayloadT], Generic[PayloadT]):
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[PayloadT]] = {}

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        return self._active.get(source_key)

    def replace_active(self, projection: ProjectionRecord[PayloadT]) -> ProjectionRecord[PayloadT]:
        self._active[projection.source_key] = projection
        return projection


class InProcessUsersRegistryStore(UsersRegistryStore):
    def __init__(self) -> None:
        self._snapshot = UsersRegistrySnapshot()
        self._revision = 0

    def load(self) -> UsersRegistrySnapshot:
        return self._snapshot

    def replace(
        self, users: tuple[UserRecord, ...], *, expected_version: str | None
    ) -> UsersRegistrySnapshot:
        if self._snapshot.version != expected_version:
            raise UsersRegistryConflictError('Users registry changed concurrently')
        self._revision += 1
        self._snapshot = UsersRegistrySnapshot(users=users, version=f'local-{self._revision}')
        return self._snapshot


class InProcessUsersAdministrationStore(UsersAdministrationStore):
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}

    def get(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def list_users(self) -> tuple[UserRecord, ...]:
        return tuple(sorted(self._users.values(), key=lambda user: user.user_id))

    def create(self, user: UserRecord) -> UserRecord:
        if user.user_id in self._users:
            raise UserAlreadyPromotedError('User is already promoted')
        self._users[user.user_id] = user
        return user

    def replace(self, user: UserRecord) -> UserRecord:
        if user.user_id not in self._users:
            raise ValueError('Promoted user does not exist')
        self._users[user.user_id] = user
        return user


@contextmanager
def open_local_configuration_manager(
    *,
    reader: ManagerConfigurationReader,
    principal_provider: Callable[[], ManagerPrincipal],
    base_root: Path | None = None,
) -> Iterator[ConfigurationManagerDependencies]:
    if reader.environment is not WebEnvironment.LOCAL:
        raise ValueError('Local Manager requires local Web environment')
    if reader.manager_provider != 'local':
        raise ValueError('Local Manager requires local provider')
    if not callable(principal_provider):
        raise TypeError('principal_provider must be callable')
    values = reader.storage()
    root = (base_root if base_root is not None else Path.cwd() / '.runtime').expanduser()
    if not root.is_absolute():
        raise ValueError('Local Manager base root must be absolute')
    namespace = COMMAND_CENTER_NAMESPACE
    persistence = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.LOCAL,
            projection_provider=AlarmConfigurationProjectionProvider.LOCAL,
            local_source_root=namespace.local_tool_root(root),
            local_projection_root=(
                namespace.local_projection_root(root) / ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME
            ),
        ),
    )
    administration = compose_command_center_administration(
        stores=CommandCenterAdministrationStores(
            profiles_source=persistence.source,
            navigation_source=persistence.source,
            profiles=InProcessProjectionStore[ProfileCatalog](),
            navigation=InProcessProjectionStore[NavigationConfigurationCatalog](),
            users_registry=InProcessUsersRegistryStore(),
            users_promoted=InProcessUsersAdministrationStore(),
        ),
        principal_provider=principal_provider,
        source_name='Local Source',
        projection_name='In-process Projection',
    )
    with ExitStack() as stack:
        storage = StorageClient(settings=catalog_storage_settings(values))
        stack.callback(storage.close)
        catalog = BlobToolCatalogStore(
            storage=storage,
            settings=BlobToolCatalogStoreSettings(
                container_name=values[STORAGE_CONTAINER_VARIABLE],
                blob_name=COMMAND_CENTER_CATALOG_BLOB_NAME,
            ),
        )
        yield ConfigurationManagerDependencies(
            source_store=persistence.source,
            projection_store=persistence.projection,
            principal_provider=principal_provider,
            tool_reference_reader=AlarmToolReferenceReader(store=catalog),
            tool_catalog_manager=ToolCatalogManagerService(
                catalog=catalog,
                connection_provider=reader.external,
            ),
            source_name='Local Source',
            projection_name='Local Projection',
            administration=administration,
        )
