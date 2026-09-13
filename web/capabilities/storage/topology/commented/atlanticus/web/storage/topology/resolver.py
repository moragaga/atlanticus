from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from atlanticus.web.storage.topology.errors import (
    ForbiddenStorageResourceOverrideError,
    MissingStorageConnectionBindingError,
    StoragePhysicalResourceConflictError,
    StorageResourceDeclarationConflictError,
    StorageResourceOverrideConflictError,
    StorageTopologyConfigurationError,
    UnknownStorageResourceOverrideError,
)
from atlanticus.web.storage.topology.models import (
    ResolvedStoragePlan,
    ResolvedStorageResource,
    StorageResourceContract,
    StorageResourceOverride,
    StorageResourceOverrideField,
)


# Resuelve declaraciones puras. Esta función no conoce SDKs, secretos ni realiza I/O.
def resolve_storage_plan(
    contracts: Sequence[StorageResourceContract[Any]],
    overrides: Sequence[StorageResourceOverride] = (),
) -> ResolvedStoragePlan:
    # Primero cerramos conflictos lógicos; ningún provider puede ser invocado desde esta capa.
    contracts_by_id = _contracts_by_logical_id(contracts)
    overrides_by_id = _overrides_by_logical_id(overrides)

    # Ordenar el error también hace determinista el resultado cuando hay más de un override desconocido.
    unknown_override_ids = sorted(overrides_by_id.keys() - contracts_by_id.keys())
    if unknown_override_ids:
        raise UnknownStorageResourceOverrideError(logical_id=unknown_override_ids[0])

    resources: list[ResolvedStorageResource[Any]] = []
    # La identidad física incluye provider y conexión; el mismo nombre puede existir legítimamente en otra conexión.
    physical_owners: dict[tuple[str, str, str], str] = {}

    # El orden por logical_id desacopla el plan del orden en que las capabilities fueron registradas.
    for logical_id in sorted(contracts_by_id):
        contract = contracts_by_id[logical_id]
        override = overrides_by_id.get(logical_id)
        connection_ref = contract.default_connection_ref
        physical_name = contract.default_physical_name

        if override is not None:
            if override.connection_ref is not None:
                _require_override_allowed(
                    contract=contract,
                    field=StorageResourceOverrideField.CONNECTION_REF,
                )
                connection_ref = override.connection_ref
            if override.physical_name is not None:
                _require_override_allowed(
                    contract=contract,
                    field=StorageResourceOverrideField.PHYSICAL_NAME,
                )
                physical_name = override.physical_name

        # Una conexión composition-bound debe quedar resuelta aquí, antes de construir cualquier bridge físico.
        if connection_ref is None:
            raise MissingStorageConnectionBindingError(logical_id=logical_id)

        resource = ResolvedStorageResource(
            logical_id=contract.logical_id,
            owner=contract.owner,
            provider=contract.provider,
            connection_ref=connection_ref,
            physical_name=physical_name,
            topology=contract.topology,
        )
        physical_key = (resource.provider, resource.connection_ref, resource.physical_name)
        conflicting_logical_id = physical_owners.get(physical_key)
        if conflicting_logical_id is not None:
            raise StoragePhysicalResourceConflictError(
                logical_id=resource.logical_id,
                conflicting_logical_id=conflicting_logical_id,
                provider=resource.provider,
                connection_ref=resource.connection_ref,
                physical_name=resource.physical_name,
            )
        physical_owners[physical_key] = resource.logical_id
        resources.append(resource)

    return ResolvedStoragePlan(resources=tuple(resources))


# Dedupe solo es válido cuando dos declaraciones del mismo logical_id son exactamente iguales.
def _contracts_by_logical_id(
    contracts: Sequence[StorageResourceContract[Any]],
) -> dict[str, StorageResourceContract[Any]]:
    normalized = _normalize_sequence(
        contracts,
        field_name='contracts',
        expected_type=StorageResourceContract,
    )
    result: dict[str, StorageResourceContract[Any]] = {}
    for contract in normalized:
        existing = result.get(contract.logical_id)
        if existing is None:
            result[contract.logical_id] = contract
        elif existing != contract:
            raise StorageResourceDeclarationConflictError(logical_id=contract.logical_id)
    return result


# Aplicamos la misma regla a overrides para evitar que el orden de configuración decida silenciosamente el ganador.
def _overrides_by_logical_id(
    overrides: Sequence[StorageResourceOverride],
) -> dict[str, StorageResourceOverride]:
    normalized = _normalize_sequence(
        overrides,
        field_name='overrides',
        expected_type=StorageResourceOverride,
    )
    result: dict[str, StorageResourceOverride] = {}
    for override in normalized:
        existing = result.get(override.logical_id)
        if existing is None:
            result[override.logical_id] = override
        elif existing != override:
            raise StorageResourceOverrideConflictError(logical_id=override.logical_id)
    return result


# Rechazamos mappings y texto para evitar iteraciones accidentales sobre keys o caracteres.
def _normalize_sequence(
    values: Sequence[Any],
    *,
    field_name: str,
    expected_type: type[Any],
) -> tuple[Any, ...]:
    if isinstance(values, str | bytes | bytearray | Mapping):
        raise StorageTopologyConfigurationError(f'{field_name} must be a sequence')
    try:
        normalized = tuple(values)
    except TypeError:
        raise StorageTopologyConfigurationError(f'{field_name} must be a sequence') from None
    if any(not isinstance(value, expected_type) for value in normalized):
        raise StorageTopologyConfigurationError(
            f'{field_name} must contain {expected_type.__name__} values'
        )
    return normalized


# Cada capability decide explícitamente qué bindings puede sustituir una composición.
def _require_override_allowed(
    *,
    contract: StorageResourceContract[Any],
    field: StorageResourceOverrideField,
) -> None:
    if field not in contract.allowed_overrides:
        raise ForbiddenStorageResourceOverrideError(
            logical_id=contract.logical_id,
            field_name=field.value,
        )
