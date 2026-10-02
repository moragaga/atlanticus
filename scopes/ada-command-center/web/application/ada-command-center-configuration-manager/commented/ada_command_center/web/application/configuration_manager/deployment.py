# Espejo pedagógico equivalente al código productivo.
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    CommandCenterDurableRuntime,
    open_command_center_durable_runtime,
)
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.storage.preparation import (
    BlobContainerResource,
    ResourceObserver,
    ResourcePreparationConnections,
    ResourcePreparationReport,
    ResourcePreparationResources,
    prepare_resources,
)

_STORAGE_CONNECTION_REF = 'command-center-storage'


# Command Center solo adapta su contenedor Blob y su plan Cosmos al contrato común.
def prepare_durable_resources(
    deployment: CommandCenterDurableRuntime,
    *,
    action: Literal['validate', 'prepare'],
    environment: WebEnvironment,
    observe_failure: ResourceObserver | None = None,
) -> ResourcePreparationReport:
    if not isinstance(deployment, CommandCenterDurableRuntime):
        raise TypeError('Resource preparation requires CommandCenterDurableRuntime')
    configuration = deployment.configuration
    # La conexión Cosmos se deriva del plan resuelto, no se duplica como configuración paralela.
    cosmos_refs = {resource.connection_ref for resource in configuration.cosmos_plan.resources}
    if len(cosmos_refs) != 1:
        raise ValueError('Command Center durable resources require one Cosmos connection')
    cosmos_ref = next(iter(cosmos_refs))
    # La semántica prepare/validate vive exclusivamente en Atlanticus.
    return prepare_resources(
        resources=ResourcePreparationResources(
            blob_containers=(
                BlobContainerResource(
                    logical_id=_STORAGE_CONNECTION_REF,
                    connection_ref=_STORAGE_CONNECTION_REF,
                    container_name=configuration.storage_container_name,
                ),
            ),
            cosmos_plan=configuration.cosmos_plan,
        ),
        connections=ResourcePreparationConnections(
            storage={_STORAGE_CONNECTION_REF: deployment.storage},
            cosmos={cosmos_ref: deployment.cosmos},
        ),
        action=action,
        environment=environment,
        observe_failure=observe_failure,
    )


def manager_resources_main(argv: Sequence[str] | None = None) -> None:
    import json
    from argparse import ArgumentParser

    from atlanticus.web.observability import configure_web_observability

    parser = ArgumentParser(description='Validate or prepare Command Center durable resources')
    parser.add_argument('action', choices=('validate', 'prepare'))
    options = parser.parse_args(argv)
    observer = configure_web_observability(
        application='ada-command-center-resource-preparation',
        json_output=True,
    )

    def observe_failure(result):
        observer.error(
            'ada.command_center.resource.preparation.failed',
            'Resource preparation failed',
            resource_kind=result.kind,
            logical_id=result.logical_id,
            physical_name=result.physical_name,
            status=result.status.value,
            error_type=result.error_type,
        )

    try:
        reader = ManagerConfigurationReader(root=Path.cwd())
        with open_command_center_durable_runtime(reader=reader) as deployment:
            report = prepare_durable_resources(
                deployment,
                action=options.action,
                environment=reader.environment,
                observe_failure=observe_failure,
            )
    except Exception as error:
        observer.error(
            'ada.command_center.resource.preparation.unavailable',
            'Resource preparation could not be started',
            error_type=type(error).__name__,
        )
        raise SystemExit(2) from error
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    if report.status != 'COMPLETED':
        raise SystemExit(1)
