from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LeyesRowDefinition:
    key: str
    label: str
    hora_key: str
    turno_key: str
    dia_key: str
    plan_key: str


LEYES_DEFINITIONS = (
    LeyesRowDefinition(
        'ley_cu', 'Ley CuT %', 'ley_cu_hora', 'ley_cu_turno', 'ley_cu_dia', 'ley_cu_plan'
    ),
    LeyesRowDefinition(
        'ley_mo', 'Ley Mo ppm', 'ley_mo_hora', 'ley_mo_turno', 'ley_mo_dia', 'ley_mo_plan'
    ),
    LeyesRowDefinition(
        'ley_conc', 'Ley Conc %', 'ley_conc_hora', 'ley_conc_turno', 'ley_conc_dia', 'ley_conc_plan'
    ),
    LeyesRowDefinition(
        'dureza', 'Dureza %', 'dureza_hora', 'dureza_turno', 'dureza_dia', 'dureza_plan'
    ),
    LeyesRowDefinition(
        'recuperacion',
        'Recuperación',
        'recuperacion_hora',
        'recuperacion_turno',
        'recuperacion_dia',
        'recuperacion_plan',
    ),
    LeyesRowDefinition('axb', 'AxB Alim', 'axb_hora', 'axb_turno', 'axb_dia', 'axb_plan'),
    LeyesRowDefinition(
        'arsenico',
        'Arsénico ppm',
        'arsenico_hora',
        'arsenico_turno',
        'arsenico_dia',
        'arsenico_plan',
    ),
)
