# Espejo pedagógico del código productivo: mismos contratos y ejecución.
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada.processes.alarm_historian.composition import build_composition
from ada.processes.alarm_historian.settings import AlarmHistorianSettingsError, configuration_specs
from atlanticus.configuration import ConfigurationBootstrap, ResolvedConfiguration, SecretsManifest
from atlanticus.connectivity.key_vault import (
    KeyVaultClient,
    KeyVaultConfigurationError,
    KeyVaultSettings,
)
from atlanticus.runtime import RuntimeExecutionResult

_COMPANY_VARIABLE = 'COMPANY_ABREV'
_PRODUCT_VARIABLE = 'PRODUCT_ABREV'


# Valida el ambiente antes de abrir conexiones o crear clientes.
def load_configuration(
    *, process_root: str | Path, environ: Mapping[str, str] | None = None
) -> ResolvedConfiguration:
    source_values = os.environ if environ is None else environ
    root = Path(process_root)
    specs = configuration_specs()
    bootstrap = ConfigurationBootstrap.from_process(
        specs=specs,
        process_values=source_values,
        configuration_root=root,
    )
    # En local solo se consulta .env y el ambiente actual.
    if bootstrap.environment.is_local:
        resolved = bootstrap.load(process_values=source_values)
    else:
        manifest = SecretsManifest.from_path(root / 'secrets.json')
        configured_keys = frozenset(spec.key for spec in specs)
        # Se usa Key Vault solamente si un valor consumido lo requiere.
        secret_entries = tuple(
            entry
            for entry in manifest.entries
            if entry.var_name in configured_keys and entry.exists_in_key_vault
        )
        if not secret_entries:
            resolved = ConfigurationBootstrap(
                environment=bootstrap.environment,
                specs=specs,
                secrets_manifest=manifest,
            ).load(process_values=source_values)
        else:
            try:
                key_vault = KeyVaultSettings(
                    company_abrev=_required_bootstrap_value(
                        {**manifest.static_values(), **source_values}, _COMPANY_VARIABLE
                    ),
                    product_abrev=_required_bootstrap_value(
                        {**manifest.static_values(), **source_values}, _PRODUCT_VARIABLE
                    ),
                    environment=bootstrap.environment,
                )
            except KeyVaultConfigurationError as error:
                raise AlarmHistorianSettingsError(str(error)) from error
            with KeyVaultClient(settings=key_vault) as resolver:
                resolved = ConfigurationBootstrap(
                    environment=bootstrap.environment,
                    specs=specs,
                    secrets_manifest=manifest,
                    secret_resolver=resolver,
                ).load(process_values=source_values)
    # La raíz durable debe ser absoluta en cualquier ambiente.
    if not Path(resolved.require('VOLUMEN_PATH')).is_absolute():
        raise AlarmHistorianSettingsError('VOLUMEN_PATH must be an absolute path')
    return resolved


# Carga configuración antes de construir e iniciar el proceso.
def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    root = Path.cwd() if process_root is None else Path(process_root)
    configuration = load_configuration(process_root=root, environ=environ)
    return build_composition(configuration=configuration).execute(argv=argv)


# Punto de entrada del comando de distribución.
def main() -> None:
    run()


# Rechaza identidades incompletas para evitar secretos del vault incorrecto.
def _required_bootstrap_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise AlarmHistorianSettingsError(f'{key} is required to resolve Key Vault')
    if value != value.strip():
        raise AlarmHistorianSettingsError(f'{key} must not contain surrounding whitespace')
    return value
