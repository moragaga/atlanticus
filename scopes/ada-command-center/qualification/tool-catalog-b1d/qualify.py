from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolSourceService,
    validate_ada_operational_tool_configuration,
)
from ada.web.tools.configuration.projection_record import TOOL_PROJECTION_DOCUMENT_TYPE
from ada.web.tools.persistence import (
    DEFAULT_TOOL_SOURCE_KEY,
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolProjectionResolutionState,
    ToolSourceProvider,
    compose_tool_persistence,
    project_current_tool_source,
)
from ada.web.tools.projection.cosmos import TOOL_PROJECTION_STORAGE_RESOURCE
from ada_command_center.tools.catalog import BlobToolCatalogStore, BlobToolCatalogStoreSettings
from ada_command_center.tools.discovery_cosmos.connections import (
    ToolCosmosConnectionConfigurationError,
)
from ada_command_center.tools.discovery_cosmos.manager import ToolCatalogManagerService
from ada_command_center.web.alarms.configuration import AlarmConfigurationSourceService
from ada_command_center.web.alarms.configuration.source_projection import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.projection.cosmos.storage import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    COMMAND_CENTER_CATALOG_BLOB_NAME,
    COMMAND_CENTER_NAMESPACE,
    STORAGE_CONTAINER_VARIABLE,
    CommandCenterConfigurationError,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.composition import (
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
    resolve_durable_configuration,
)
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerSpec,
    CosmosProvisioner,
    CosmosQueryParameter,
)
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.projection.models import ProjectionAlignment

_ROOT = Path(__file__).resolve().parents[4]
_MANAGER_ROOT = (
    _ROOT / 'scopes/ada-command-center/web/application/ada-command-center-configuration-manager'
)
_FIXTURES = Path(__file__).resolve().parent / 'fixtures'
_TOOLS = {
    'process': ('validation_process', 'validation_process'),
    'integrated': ('validation_integrated', 'validation_integrated'),
}


class QualificationError(RuntimeError):
    pass


def fixture(tool: str) -> ToolConfiguration:
    if tool not in _TOOLS:
        raise QualificationError('Unknown qualification tool')
    path = _FIXTURES / f'{tool}.json'
    configuration = ToolConfiguration.from_document(json.loads(path.read_text(encoding='utf-8')))
    validate_ada_operational_tool_configuration(configuration)
    if configuration.tool_key != _TOOLS[tool][0]:
        raise QualificationError('Qualification Tool key does not match its fixture')
    return configuration


def validate_fixtures() -> dict[str, object]:
    tools = tuple(fixture(name) for name in _TOOLS)
    if len({tool.tool_key for tool in tools}) != len(tools):
        raise QualificationError('Qualification Tool keys are not unique')
    return {'status': 'VALID', 'tools': [tool.tool_key for tool in tools]}


def _reader() -> ManagerConfigurationReader:
    reader = ManagerConfigurationReader(root=_MANAGER_ROOT)
    if reader.environment.is_production:
        raise QualificationError('Run this qualification only in a local Web environment')
    return reader


def _settings(reader: ManagerConfigurationReader, name: str):
    if name not in _TOOLS:
        raise QualificationError('Unknown qualification Tool connection')
    external = reader.external()
    if name not in external:
        raise QualificationError(f'Qualification connection is not configured: {name}')
    return external[name]


def preflight(reader: ManagerConfigurationReader) -> dict[str, object]:
    validate_fixtures()
    external = reader.external()
    declared = set(external)
    expected = set(_TOOLS)
    if declared != expected:
        raise QualificationError(
            'Use isolated connections containing exactly process and integrated'
        )
    database_ids = {(external[name].endpoint, external[name].database_name) for name in _TOOLS}
    if len(database_ids) != len(_TOOLS):
        raise QualificationError('Qualification Tools must use separate Cosmos databases')
    if reader.manager_provider == 'durable':
        own = resolve_durable_configuration(reader.own(), local=True).cosmos_settings
        if (own.endpoint, own.database_name) in database_ids:
            raise QualificationError('Command Center must use its own Cosmos database')
    reader.storage()
    return {
        'status': 'READY',
        'provider': reader.manager_provider,
        'connections': sorted(external),
        'tools': list(_TOOLS),
        'catalog_blob': COMMAND_CENTER_CATALOG_BLOB_NAME,
    }


def _spec(contract):
    return CosmosContainerSpec(
        name=contract.default_physical_name,
        partition_key_path=contract.topology.partition_key_path,
        default_ttl_seconds=contract.topology.default_ttl_seconds,
    )


def prepare(reader: ManagerConfigurationReader, *, apply: bool) -> dict[str, object]:
    preflight(reader)
    resources = {}
    with ExitStack() as stack:
        for name in _TOOLS:
            client = CosmosClient(settings=_settings(reader, name))
            stack.callback(client.close)
            provisioner = CosmosProvisioner(client=client)
            if apply:
                provisioner.ensure_database()
                created = provisioner.ensure_containers((_spec(TOOL_PROJECTION_STORAGE_RESOURCE),))
            else:
                provisioner.validate_containers((_spec(TOOL_PROJECTION_STORAGE_RESOURCE),))
                created = ()
            resources[name] = {'checked': True, 'created_containers': list(created)}
        if reader.manager_provider == 'durable':
            own = resolve_durable_configuration(reader.own(), local=True)
            client = CosmosClient(settings=own.cosmos_settings)
            stack.callback(client.close)
            provisioner = CosmosProvisioner(client=client)
            if apply:
                provisioner.ensure_database()
                created = provisioner.ensure_containers(
                    (_spec(ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE),)
                )
            else:
                provisioner.validate_containers(
                    (_spec(ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE),)
                )
                created = ()
            resources['command_center'] = {'checked': True, 'created_containers': list(created)}
    return {'status': 'PREPARED' if apply else 'VALID', 'resources': resources}


@contextmanager
def _tool_runtime(
    reader: ManagerConfigurationReader, name: str
) -> Iterator[tuple[object, CosmosClient]]:
    with ExitStack() as stack:
        client = CosmosClient(settings=_settings(reader, name))
        stack.callback(client.close)
        storage = StorageClient(settings=catalog_storage_settings(reader.storage()))
        stack.callback(storage.close)
        configuration = ToolPersistenceSettings(
            namespace=AdaStorageNamespace(
                COMMAND_CENTER_NAMESPACE.application_namespace, _TOOLS[name][1]
            ),
            source_provider=ToolSourceProvider.BLOB,
            projection_provider=ToolProjectionProvider.COSMOS,
            blob_container_name=reader.storage()[STORAGE_CONTAINER_VARIABLE],
            cosmos_container_name=TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name,
        )
        yield (
            compose_tool_persistence(
                settings=configuration,
                storage_client=storage,
                cosmos_client=client,
            ),
            client,
        )


def publish_tool(
    reader: ManagerConfigurationReader, name: str, *, replace: bool
) -> dict[str, object]:
    configuration = fixture(name)
    with _tool_runtime(reader, name) as (composition, _):
        source = ToolSourceService(source=composition.source, source_key=DEFAULT_TOOL_SOURCE_KEY)
        current = source.get_current()
        existing = source.load_current() if current.current is not None else None
        if existing is not None and not replace:
            raise QualificationError(
                'Tool Source already exists; use --replace for an explicit release'
            )
        result = source.publish_configuration(
            configuration,
            published_by='qualification-manual',
            expected_concurrency_token=current.concurrency_token,
            basis_release=None if current.current is None else current.current.release_ref,
        )
        return {
            'status': 'SOURCE_PUBLISHED',
            'tool': name,
            'source_release_id': result.release.release_ref.release_id.value,
            'next': f'project-tool {name}',
        }


def project_tool(reader: ManagerConfigurationReader, name: str) -> dict[str, object]:
    with _tool_runtime(reader, name) as (composition, _):
        result = project_current_tool_source(composition)
        if result.state is not ToolProjectionResolutionState.READY or result.projection is None:
            raise QualificationError(f'Tool projection is not READY: {result.state.value}')
        return {
            'status': 'PROJECTED',
            'tool': name,
            'source_release_id': result.projection.source_release_id.value,
        }


def verify_tool(reader: ManagerConfigurationReader, name: str) -> dict[str, object]:
    expected = fixture(name)
    with _tool_runtime(reader, name) as (composition, client):
        source = ToolSourceService(source=composition.source, source_key=DEFAULT_TOOL_SOURCE_KEY)
        release = source.load_current()
        active = composition.projection.get_active(DEFAULT_TOOL_SOURCE_KEY)
        if release is None or active is None:
            raise QualificationError('Tool Source or active Projection is missing')
        if release.configuration != expected or active.payload != expected:
            raise QualificationError('Tool Source and Projection differ from the fixture')
        if active.source_release_id != release.release_ref.release_id:
            raise QualificationError('Tool Source and Projection release IDs differ')
        status = composition.projection_service.get_status(DEFAULT_TOOL_SOURCE_KEY)
        if status.alignment is not ProjectionAlignment.CURRENT:
            raise QualificationError('Tool Projection does not match the current Source')
        namespace = composition.settings.namespace.tool_prefix
        raw = client.query_items(
            container_name=TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name,
            query=(
                'SELECT c.id, c.partition_key, c.source_release_id FROM c '
                'WHERE c.document_type = @type AND c.source_key = @source '
                'AND c.partition_key = @partition'
            ),
            parameters=(
                CosmosQueryParameter(name='@type', value=TOOL_PROJECTION_DOCUMENT_TYPE),
                CosmosQueryParameter(name='@source', value=DEFAULT_TOOL_SOURCE_KEY.value),
                CosmosQueryParameter(name='@partition', value=namespace),
            ),
            cross_partition=True,
            max_items=2,
            page_size=2,
        )
        if len(raw) != 1 or raw[0].get('source_release_id') != active.source_release_id.value:
            raise QualificationError('Physical Cosmos projection does not match the adapter')
        return {
            'status': 'VERIFIED',
            'tool_key': active.payload.tool_key,
            'namespace': namespace,
            'source_release_id': active.source_release_id.value,
        }


@contextmanager
def _catalog(reader: ManagerConfigurationReader) -> Iterator[BlobToolCatalogStore]:
    with ExitStack() as stack:
        storage = StorageClient(settings=catalog_storage_settings(reader.storage()))
        stack.callback(storage.close)
        yield BlobToolCatalogStore(
            storage=storage,
            settings=BlobToolCatalogStoreSettings(
                container_name=reader.storage()[STORAGE_CONTAINER_VARIABLE],
                blob_name=COMMAND_CENTER_CATALOG_BLOB_NAME,
            ),
        )


def inspect_catalog(reader: ManagerConfigurationReader) -> dict[str, object]:
    preflight(reader)
    with _catalog(reader) as catalog:
        current = catalog.get_current()
        if current is not None and {item.tool_key for item in current.tools} - {
            key for key, _ in _TOOLS.values()
        }:
            raise QualificationError('Use an isolated Blob container without unrelated Tools')
        review = ToolCatalogManagerService(
            catalog=catalog, connection_provider=reader.external
        ).inspect()
    statuses = {item.connection_name: item.status for item in review.connections}
    found = {
        item.connection_name: {tool.tool_key for tool in item.tools} for item in review.connections
    }
    expected = {name: key for name, (key, _) in _TOOLS.items()}
    ready = all(
        statuses.get(name) == 'READY' and expected[name] in found.get(name, set())
        for name in expected
    )
    return {
        'status': 'READY' if ready and review.can_confirm else 'BLOCKED',
        'can_confirm': bool(ready and review.can_confirm),
        'connection_statuses': statuses,
        'candidate_keys': {name: sorted(keys) for name, keys in found.items()},
        'current_revision': review.current_revision,
        'issue': review.issue,
    }


def verify_catalog(reader: ManagerConfigurationReader) -> dict[str, object]:
    with _catalog(reader) as catalog:
        current = catalog.get_current()
    if current is None:
        raise QualificationError('Confirmed Tool Catalog does not exist in Storage')
    if {item.tool_key for item in current.tools} != {key for key, _ in _TOOLS.values()}:
        raise QualificationError('Qualification Catalog must contain exactly the two test Tools')
    releases = {}
    for name, (key, _) in _TOOLS.items():
        with _tool_runtime(reader, name) as (composition, _):
            active = composition.projection.get_active(DEFAULT_TOOL_SOURCE_KEY)
            entry = current.get(key)
            if active is None or entry is None:
                raise QualificationError(f'Confirmed catalog or Tool projection is missing: {name}')
            if (
                entry.source_release_id != active.source_release_id
                or entry.display_name != active.payload.display_name
                or entry.kind is not active.payload.kind
                or entry.structure != active.payload.structure
            ):
                raise QualificationError(f'Confirmed Tool entry is out of sync: {name}')
            releases[name] = entry.source_release_id.value
    return {'status': 'VERIFIED', 'revision': current.revision, 'releases': releases}


def verify_alarm(reader: ManagerConfigurationReader) -> dict[str, object]:
    if reader.manager_provider != 'durable':
        raise QualificationError('Alarm Cosmos qualification requires durable provider')
    principal = ManagerPrincipal(
        subject_id='qualification', display_name='Qualification', access_keys=('alarms.manage',)
    )
    with open_durable_configuration_manager(
        reader=reader, principal_provider=lambda: principal
    ) as dependencies:
        source = AlarmConfigurationSourceService(
            source=dependencies.source_store, source_key=ALARM_CONFIGURATION_SOURCE_KEY
        )
        published = source.load_current()
        active = dependencies.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
        catalog = dependencies.tool_reference_reader.load()
        if published is None or active is None or catalog is None:
            raise QualificationError('Alarm Source, Projection, or confirmed catalog is absent')
        service = create_alarm_configuration_projection_service(
            source=dependencies.source_store, projection=dependencies.projection_store
        )
        if (
            service.get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment
            is not ProjectionAlignment.CURRENT
        ):
            raise QualificationError('Alarm Projection is not aligned with its Source')
        if active.payload != published.snapshot:
            raise QualificationError('Alarm Projection differs from the published Source')
        if published.snapshot.confirmed_tool_catalog_revision != catalog.catalog_revision:
            raise QualificationError('Alarm Source is not pinned to the current Tool Catalog')
        selected = published.snapshot.tool_dependencies
        expected_keys = {key for key, _ in _TOOLS.values()}
        if not expected_keys.issubset({tool.tool_key for tool in selected.tools}):
            raise QualificationError('Alarm publication must reference both qualification Tools')
        for tool in selected.tools:
            reference = catalog.dependencies.get(tool.tool_key)
            if reference != tool:
                raise QualificationError('Alarm Source contains a mismatched Tool dependency')
        return {
            'status': 'VERIFIED',
            'alarm_release_id': published.release_ref.release_id.value,
            'catalog_revision': catalog.catalog_revision,
            'selected_tools': sorted(tool.tool_key for tool in selected.tools),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='B1d external qualification using existing ADA stores'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate-fixtures')
    commands.add_parser('preflight')
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('--apply', action='store_true')
    publisher = commands.add_parser('publish-tool')
    publisher.add_argument('tool', choices=tuple(_TOOLS))
    publisher.add_argument('--replace', action='store_true')
    projector = commands.add_parser('project-tool')
    projector.add_argument('tool', choices=tuple(_TOOLS))
    verifier = commands.add_parser('verify-tool')
    verifier.add_argument('tool', choices=tuple(_TOOLS))
    commands.add_parser('inspect-catalog')
    commands.add_parser('verify-catalog')
    commands.add_parser('verify-alarm')
    args = parser.parse_args()
    try:
        if args.command == 'validate-fixtures':
            report = validate_fixtures()
        else:
            reader = _reader()
            if args.command == 'preflight':
                report = preflight(reader)
            elif args.command == 'prepare':
                report = prepare(reader, apply=args.apply)
            elif args.command == 'publish-tool':
                report = publish_tool(reader, args.tool, replace=args.replace)
            elif args.command == 'project-tool':
                report = project_tool(reader, args.tool)
            elif args.command == 'verify-tool':
                report = verify_tool(reader, args.tool)
            elif args.command == 'inspect-catalog':
                report = inspect_catalog(reader)
            elif args.command == 'verify-catalog':
                report = verify_catalog(reader)
            else:
                report = verify_alarm(reader)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if report['status'] == 'BLOCKED':
            return 1
        return 0
    except Exception as error:
        issue = {'status': 'ERROR', 'error_type': type(error).__name__}
        if isinstance(error, QualificationError):
            issue['issue'] = str(error)
        elif isinstance(
            error,
            (ToolCosmosConnectionConfigurationError, CommandCenterConfigurationError),
        ):
            issue['issue'] = str(error)
            issue['configuration_source'] = str(_MANAGER_ROOT / '.env')
            issue['hint'] = (
                'The runner reads the Manager .env or process environment; '
                'the qualification .env.detail is documentation only.'
            )
        print(json.dumps(issue, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
