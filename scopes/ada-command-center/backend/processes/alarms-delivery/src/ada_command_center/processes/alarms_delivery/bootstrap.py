from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ada_command_center.processes.alarms_delivery.job import build_delivery_input_job
from ada_command_center.processes.alarms_delivery.settings import (
    AlarmDeliverySettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationBootstrap, ResolvedConfiguration
from atlanticus.runtime import RuntimeConfiguration, RuntimeExecutionResult


def load_configuration(
    *, process_root: str | Path, environ: Mapping[str, str] | None = None
) -> ResolvedConfiguration:
    values = os.environ if environ is None else environ
    bootstrap = ConfigurationBootstrap.from_process(
        specs=configuration_specs(), process_values=values, configuration_root=Path(process_root)
    )
    resolved = bootstrap.load(process_values=values)
    if not Path(resolved.require('VOLUMEN_PATH')).expanduser().is_absolute():
        raise ValueError('VOLUMEN_PATH must be absolute')
    return resolved


def run(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    process_root: str | Path | None = None,
) -> RuntimeExecutionResult:
    values = os.environ if environ is None else environ
    configuration = load_configuration(
        process_root=Path.cwd() if process_root is None else process_root,
        environ=values,
    )
    settings = AlarmDeliverySettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    return build_delivery_input_job(
        runtime_configuration=runtime_configuration,
        source_key=settings.source_key,
        poll_seconds=settings.poll_seconds,
        max_facts_per_iteration=settings.max_facts_per_iteration,
    ).execute(argv=argv, environ=configuration.values)


def main() -> None:
    run()
