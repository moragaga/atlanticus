from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada.processes.alarm_modeler.composition import build_composition
from ada.processes.alarm_modeler.settings import configuration_specs
from atlanticus.configuration import (
    ConfigurationBootstrap,
    ResolvedConfiguration,
    SecretsManifest,
)
from atlanticus.connectivity.key_vault import (
    KeyVaultClient,
    KeyVaultSettings,
)
from atlanticus.runtime import RuntimeExecutionResult


def load_configuration(
    *, process_root: str | Path, environ: Mapping[str, str] | None = None
) -> ResolvedConfiguration:
    source = os.environ if environ is None else environ
    root = Path(process_root)
    specs = configuration_specs()
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs, process_values=source, configuration_root=root
    )
    environment = bootstrap.environment
    if environment.is_local:
        configuration = bootstrap.load(process_values=source)
    else:
        manifest = SecretsManifest.from_path(root / 'secrets.json')
        keys = frozenset(spec.key for spec in specs)
        secret_entries = tuple(
            entry for entry in manifest.entries
            if entry.var_name in keys and entry.exists_in_key_vault
        )
        if not secret_entries:
            configuration = ConfigurationBootstrap(
                environment=environment,
                specs=specs,
                secrets_manifest=manifest,
            ).load(process_values=source)
        else:
            values = {**manifest.static_values(), **source}
            key_vault = KeyVaultSettings(
                company_abrev=_required(values, 'COMPANY_ABREV'),
                product_abrev=_required(values, 'PRODUCT_ABREV'),
                environment=environment,
            )
            with KeyVaultClient(settings=key_vault) as resolver:
                configuration = ConfigurationBootstrap(
                    environment=environment,
                    specs=specs,
                    secrets_manifest=manifest,
                    secret_resolver=resolver,
                ).load(process_values=source)
    if not Path(configuration.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise ValueError('VOLUMEN_PATH must be an absolute path')
    return configuration


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{key} must be non-empty normalized text')
    return value


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
