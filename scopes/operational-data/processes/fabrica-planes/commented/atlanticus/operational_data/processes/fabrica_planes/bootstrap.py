# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from atlanticus.configuration import ConfigurationBootstrap, ResolvedConfiguration, SecretsManifest
from atlanticus.connectivity.key_vault import (
    KeyVaultClient,
    KeyVaultConfigurationError,
    KeyVaultSettings,
)
from atlanticus.operational_data.processes.fabrica_planes.composition import build_composition
from atlanticus.operational_data.processes.fabrica_planes.errors import (
    FabricaProcessConfigurationError,
)
from atlanticus.operational_data.processes.fabrica_planes.settings import configuration_specs
from atlanticus.runtime import RuntimeExecutionResult


# Resuelve configuración local o remota desde las fuentes autorizadas.
def load_configuration(
    *, process_root: str | Path, environ: Mapping[str, str] | None = None,
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    specs = configuration_specs()
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs, process_values=values, configuration_root=root,
    )
    environment = bootstrap.environment
    if environment.is_local:
        configuration = bootstrap.load(process_values=values)
        return _absolute_volume(configuration)
    manifest = SecretsManifest.from_path(root / 'secrets.json')
    secret_keys = {spec.key for spec in specs}
    required_secrets = tuple(
        entry for entry in manifest.entries
        if entry.var_name in secret_keys and entry.exists_in_key_vault
    )
    if not required_secrets:
        configuration = ConfigurationBootstrap(
            environment=environment, specs=specs, secrets_manifest=manifest,
        ).load(process_values=values)
        return _absolute_volume(configuration)
    combined = {**manifest.static_values(), **values}
    try:
        vault = KeyVaultSettings(
            company_abrev=_bootstrap_value(combined, 'COMPANY_ABREV'),
            product_abrev=_bootstrap_value(combined, 'PRODUCT_ABREV'),
            environment=environment,
        )
    except KeyVaultConfigurationError as error:
        raise FabricaProcessConfigurationError(str(error)) from error
    with KeyVaultClient(settings=vault) as resolver:
        configuration = ConfigurationBootstrap(
            environment=environment, specs=specs,
            secrets_manifest=manifest, secret_resolver=resolver,
        ).load(process_values=values)
    return _absolute_volume(configuration)


# Responsabilidad de run.
def run(
    *, argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    root = Path.cwd() if process_root is None else Path(process_root)
    configuration = load_configuration(process_root=root, environ=environ)
    return build_composition(configuration=configuration).execute(argv=argv)


# Responsabilidad de main.
def main() -> None:
    run()


# Responsabilidad de _bootstrap_value.
def _bootstrap_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise FabricaProcessConfigurationError(f'{key} is required to resolve Key Vault')
    return value


# Responsabilidad de _absolute_volume.
def _absolute_volume(configuration: ResolvedConfiguration) -> ResolvedConfiguration:
    if not Path(configuration.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise FabricaProcessConfigurationError('VOLUMEN_PATH must be an absolute path')
    return configuration
