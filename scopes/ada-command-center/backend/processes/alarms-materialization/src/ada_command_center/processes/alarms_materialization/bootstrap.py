from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada_command_center.processes.alarms_materialization.composition import build_composition
from ada_command_center.processes.alarms_materialization.settings import (
    AlarmMaterializationSettingsError,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationBootstrap, ResolvedConfiguration, SecretsManifest
from atlanticus.connectivity.key_vault import (
    KeyVaultClient,
    KeyVaultConfigurationError,
    KeyVaultSettings,
)
from atlanticus.runtime import RuntimeExecutionResult


def load_configuration(
    *, process_root: str | Path, environ: Mapping[str, str] | None = None
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    specs = configuration_specs()
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs, process_values=values, configuration_root=root
    )
    if bootstrap.environment.is_local:
        return _require_volume(bootstrap.load(process_values=values))
    manifest = SecretsManifest.from_path(root / 'secrets.json')
    relevant = frozenset(spec.key for spec in specs)
    if not any(item.var_name in relevant and item.exists_in_key_vault for item in manifest.entries):
        return _require_volume(
            ConfigurationBootstrap(
                environment=bootstrap.environment, specs=specs, secrets_manifest=manifest
            ).load(process_values=values)
        )
    merged = {**manifest.static_values(), **values}
    try:
        settings = KeyVaultSettings(
            company_abrev=_required(merged, 'COMPANY_ABREV'),
            environment=bootstrap.environment,
            product_abrev=_required(merged, 'PRODUCT_ABREV'),
        )
    except KeyVaultConfigurationError as error:
        raise AlarmMaterializationSettingsError(str(error)) from error
    with KeyVaultClient(settings=settings) as resolver:
        configuration = ConfigurationBootstrap(
            environment=bootstrap.environment,
            specs=specs,
            secrets_manifest=manifest,
            secret_resolver=resolver,
        ).load(process_values=values)
    return _require_volume(configuration)


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlarmMaterializationSettingsError(f'{name} is required for Key Vault')
    return value


def _require_volume(configuration: ResolvedConfiguration) -> ResolvedConfiguration:
    if not Path(configuration.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise AlarmMaterializationSettingsError('VOLUMEN_PATH must be absolute')
    return configuration


def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    values = os.environ if environ is None else environ
    root = Path.cwd() if process_root is None else Path(process_root)
    configuration = load_configuration(process_root=root, environ=values)
    return build_composition(configuration=configuration).execute(argv=argv)


def main() -> None:
    run()
