from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada.processes.kpi_materialization.composition import build_composition
from ada.processes.kpi_materialization.connections import (
    KpiMaterializationConnectionRegistry,
    read_connection_registry,
)
from ada.processes.kpi_materialization.errors import KpiMaterializationSettingsError
from ada.processes.kpi_materialization.settings import configuration_specs
from atlanticus.configuration import (
    ConfigurationBootstrap,
    ResolvedConfiguration,
    SecretsManifest,
)
from atlanticus.connectivity.key_vault import (
    KeyVaultClient,
    KeyVaultConfigurationError,
    KeyVaultSettings,
)
from atlanticus.runtime import RuntimeExecutionResult


def load_configuration(
    *,
    process_root: str | Path,
    registry: KpiMaterializationConnectionRegistry | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    active_registry = registry if registry is not None else read_connection_registry(root)
    specs = (*configuration_specs(), *active_registry.configuration_specs())
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs,
        process_values=values,
        configuration_root=root,
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
            try:
                settings = KeyVaultSettings(
                    company_abrev=_required_bootstrap_value(
                        bootstrap_values,
                        'COMPANY_ABREV',
                    ),
                    product_abrev=_required_bootstrap_value(
                        bootstrap_values,
                        'PRODUCT_ABREV',
                    ),
                    environment=bootstrap.environment,
                )
            except KeyVaultConfigurationError as error:
                raise KpiMaterializationSettingsError(str(error)) from error
            with KeyVaultClient(settings=settings) as resolver:
                resolved = ConfigurationBootstrap(
                    environment=bootstrap.environment,
                    specs=specs,
                    secrets_manifest=manifest,
                    secret_resolver=resolver,
                ).load(process_values=values)
    if not Path(resolved.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise KpiMaterializationSettingsError('VOLUMEN_PATH must be absolute')
    return resolved


def _required_bootstrap_value(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise KpiMaterializationSettingsError(f'{name} is required to resolve Key Vault')
    return value


def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    values = os.environ if environ is None else environ
    root = Path.cwd() if process_root is None else Path(process_root)
    registry = read_connection_registry(root)
    configuration = load_configuration(
        process_root=root,
        registry=registry,
        environ=values,
    )
    connections = registry.resolve(
        values=configuration.values,
        environment=configuration.environment,
    )
    return build_composition(
        configuration=configuration,
        connections=connections,
    ).execute(argv=argv)


def main() -> None:
    run()
