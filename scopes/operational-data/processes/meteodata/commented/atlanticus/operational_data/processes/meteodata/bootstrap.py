from __future__ import annotations

# Se resuelve la configuración local o Key Vault sin que el productor lea variables de entorno.
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from atlanticus.configuration import ConfigurationBootstrap, ResolvedConfiguration, SecretsManifest
from atlanticus.connectivity.key_vault import KeyVaultClient, KeyVaultSettings
from atlanticus.operational_data.processes.meteodata.composition import build_composition
from atlanticus.operational_data.processes.meteodata.errors import (
    MeteodataProcessConfigurationError,
)
from atlanticus.operational_data.processes.meteodata.settings import configuration_specs
from atlanticus.runtime import RuntimeExecutionResult


def load_configuration(
    *,
    process_root: str | Path,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    root = Path(process_root)
    specs = configuration_specs()
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs,
        process_values=values,
        configuration_root=root,
    )
    environment = bootstrap.environment
    if environment.is_local:
        return _require_absolute_volume_path(bootstrap.load(process_values=values))
    manifest = SecretsManifest.from_path(root / 'secrets.json')
    entries = tuple(item for item in manifest.entries if item.exists_in_key_vault)
    if not entries:
        return _require_absolute_volume_path(
            ConfigurationBootstrap(
                environment=environment,
                specs=specs,
                secrets_manifest=manifest,
            ).load(process_values=values)
        )
    source = {**manifest.static_values(), **values}
    vault_settings = KeyVaultSettings(
        company_abrev=_required_value(source, 'COMPANY_ABREV'),
        environment=environment,
        product_abrev=_required_value(source, 'PRODUCT_ABREV'),
    )
    with KeyVaultClient(settings=vault_settings) as resolver:
        configuration = ConfigurationBootstrap(
            environment=environment,
            specs=specs,
            secrets_manifest=manifest,
            secret_resolver=resolver,
        ).load(process_values=values)
    return _require_absolute_volume_path(configuration)


def _required_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise MeteodataProcessConfigurationError(f'{key} is required')
    return value


def _require_absolute_volume_path(configuration: ResolvedConfiguration) -> ResolvedConfiguration:
    path = Path(configuration.require('VOLUMEN_PATH')).expanduser()
    if not path.is_absolute():
        raise MeteodataProcessConfigurationError('VOLUMEN_PATH must be an absolute path')
    return configuration


def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    root = Path.cwd() if process_root is None else Path(process_root)
    configuration = load_configuration(process_root=root, environ=environ)
    return build_composition(configuration=configuration).execute(argv=argv)


def main() -> None:
    run()
