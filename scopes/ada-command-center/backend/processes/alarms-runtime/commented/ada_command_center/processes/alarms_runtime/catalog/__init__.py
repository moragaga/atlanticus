# API del catálogo: el proceso decide explícitamente cuándo construirlo.

from ada_command_center.processes.alarms_runtime.catalog.registry import (
    build_alarm_evaluator_registry,
)

__all__ = ['build_alarm_evaluator_registry']
