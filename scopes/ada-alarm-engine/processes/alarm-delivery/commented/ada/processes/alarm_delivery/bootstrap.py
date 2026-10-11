# Resuelve secretos y conexiones antes del arranque; prepara Cosmos sólo bajo ENSURE.
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada.processes.alarm_delivery.composition import build_composition
from ada.processes.alarm_delivery.connections import (
    ToolConnectionRegistry,
    read_connection_registry,
)
from ada.processes.alarm_delivery.provisioning import prepare_cosmos_containers
from ada.processes.alarm_delivery.settings import AlarmDeliverySettings, configuration_specs
from atlanticus.configuration import (
    ConfigurationBootstrap,
    ResolvedConfiguration,
    SecretsManifest,
)
from atlanticus.connectivity.key_vault import KeyVaultClient, KeyVaultSettings
from atlanticus.runtime import RuntimeExecutionResult


# Conserva la resolución local y Key Vault existente, sin nuevas rutas de secretos.
def load_configuration(
    *,
    process_root: str | Path,
    registry: ToolConnectionRegistry | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    active = registry if registry is not None else read_connection_registry(root)
    specs = (*configuration_specs(), *active.specs())
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs, process_values=values, configuration_root=root
    )
    if bootstrap.environment.is_local:
        resolved = bootstrap.load(process_values=values)
    else:
        manifest = SecretsManifest.from_path(root / 'secrets.json')
        requested = frozenset(spec.key for spec in specs)
        secrets = tuple(
            entry
            for entry in manifest.entries
            if entry.var_name in requested and entry.exists_in_key_vault
        )
        if not secrets:
            resolved = ConfigurationBootstrap(
                environment=bootstrap.environment, specs=specs, secrets_manifest=manifest
            ).load(process_values=values)
        else:
            populated = {**manifest.static_values(), **values}
            vault_settings = KeyVaultSettings(
                company_abrev=_required(populated, 'COMPANY_ABREV'),
                product_abrev=_required(populated, 'PRODUCT_ABREV'),
                environment=bootstrap.environment,
            )
            with KeyVaultClient(settings=vault_settings) as resolver:
                resolved = ConfigurationBootstrap(
                    environment=bootstrap.environment,
                    specs=specs,
                    secrets_manifest=manifest,
                    secret_resolver=resolver,
                ).load(process_values=values)
    if not Path(resolved.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise ValueError('VOLUMEN_PATH must be absolute')
    return resolved


# Responsabilidad delimitada: _required
def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'{key} is required for Key Vault')
    return value


# ENSURE termina completamente antes de invocar Job Runtime; OFF no consulta contenedores.
def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    root = Path.cwd() if process_root is None else Path(process_root)
    registry = read_connection_registry(root)
    resolved = load_configuration(process_root=root, registry=registry, environ=environ)
    connections = registry.resolve(
        values=resolved.values,
        environment=resolved.environment,
    )
    settings = AlarmDeliverySettings.from_configuration(resolved)
    prepare_cosmos_containers(
        mode=settings.cosmos_provision_mode,
        connections=connections,
    )
    return build_composition(configuration=resolved, connections=connections).execute(argv=argv)


# Responsabilidad delimitada: main
def main() -> None:
    run()
