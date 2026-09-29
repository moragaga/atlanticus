from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada_command_center.processes.alarms_delivery.connections import (
    AlarmDeliveryConnectionRegistry,
    read_connection_registry,
)
from ada_command_center.processes.alarms_delivery.job import build_delivery_input_job
from ada_command_center.processes.alarms_delivery.parallel import ParallelCosmosPublisher
from ada_command_center.processes.alarms_delivery.settings import (
    AlarmDeliverySettings,
    configuration_specs,
)
from atlanticus.configuration import (
    ConfigurationBootstrap,
    ResolvedConfiguration,
    SecretsManifest,
)
from atlanticus.connectivity.key_vault import KeyVaultClient, KeyVaultSettings
from atlanticus.runtime import RuntimeConfiguration, RuntimeExecutionResult


# Primero conoce las referencias del archivo y luego resuelve todas sus variables con bootstrap.
def load_configuration(
    *,
    process_root: str | Path,
    registry: AlarmDeliveryConnectionRegistry | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    active_registry = registry if registry is not None else read_connection_registry(root)
    specs = (*configuration_specs(), *(active_registry.configuration_specs() if active_registry else ()))
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs, process_values=values, configuration_root=root
    )
    if bootstrap.environment.is_local:
        resolved = bootstrap.load(process_values=values)
    else:
        manifest = SecretsManifest.from_path(root / 'secrets.json')
        requested = frozenset(spec.key for spec in specs)
        key_vault_secrets = tuple(
            entry
            for entry in manifest.entries
            if entry.var_name in requested and entry.exists_in_key_vault
        )
        if not key_vault_secrets:
            resolved = ConfigurationBootstrap(
                environment=bootstrap.environment,
                specs=specs,
                secrets_manifest=manifest,
            ).load(process_values=values)
        else:
            bootstrap_values = {**manifest.static_values(), **values}
            company = _required_bootstrap_value(bootstrap_values, 'COMPANY_ABREV')
            product = _required_bootstrap_value(bootstrap_values, 'PRODUCT_ABREV')
            with KeyVaultClient(
                settings=KeyVaultSettings(
                    company_abrev=company,
                    product_abrev=product,
                    environment=bootstrap.environment,
                )
            ) as resolver:
                resolved = ConfigurationBootstrap(
                    environment=bootstrap.environment,
                    specs=specs,
                    secrets_manifest=manifest,
                    secret_resolver=resolver,
                ).load(process_values=values)
    if not Path(resolved.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise ValueError('VOLUMEN_PATH must be absolute')
    return resolved


# La identidad para Key Vault debe provenir del despliegue, nunca inferirse.
def _required_bootstrap_value(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{name} is required to resolve Key Vault')
    return value


# Sin archivo no se adquiere lease. Con archivo, se valida el registro una sola vez al iniciar.
def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult | None:
    values = os.environ if environ is None else environ
    root = Path.cwd() if process_root is None else Path(process_root)
    registry = read_connection_registry(root)
    if registry is None:
        return None
    configuration = load_configuration(process_root=root, registry=registry, environ=values)
    settings = AlarmDeliverySettings.from_configuration(configuration)
    connections = registry.resolve(values=configuration.values, environment=configuration.environment)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    with ParallelCosmosPublisher(connections=connections, max_workers=settings.max_workers):
        return build_delivery_input_job(
            runtime_configuration=runtime_configuration,
            source_key=settings.source_key,
            poll_seconds=settings.poll_seconds,
            max_facts_per_iteration=settings.max_facts_per_iteration,
        ).execute(argv=argv, environ=configuration.values)


# El entrypoint conserva la misma forma que los demás jobs de Atlanticus.
def main() -> None:
    run()
