from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada_command_center.processes.alarms_modeler.job import build_alarm_modeler_job
from ada_command_center.processes.alarms_modeler.settings import (
    AlarmModelerSettings,
    configuration_specs,
)
from atlanticus.configuration import (
    ConfigurationBootstrap,
    ResolvedConfiguration,
    SecretsManifest,
)
from atlanticus.connectivity.key_vault import KeyVaultClient, KeyVaultSettings
from atlanticus.runtime import RuntimeConfiguration, RuntimeExecutionResult


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
            with KeyVaultClient(
                settings=KeyVaultSettings(
                    company_abrev=_required(bootstrap_values, 'COMPANY_ABREV'),
                    product_abrev=_required(bootstrap_values, 'PRODUCT_ABREV'),
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


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{name} is required to resolve Key Vault')
    return value


def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    values = os.environ if environ is None else environ
    root = Path.cwd() if process_root is None else Path(process_root)
    configuration = load_configuration(process_root=root, environ=values)
    settings = AlarmModelerSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    return build_alarm_modeler_job(
        runtime_configuration=runtime_configuration,
        source_key=settings.source_key,
        poll_seconds=settings.poll_seconds,
    ).execute(argv=argv, environ=configuration.values)


def main() -> None:
    run()
