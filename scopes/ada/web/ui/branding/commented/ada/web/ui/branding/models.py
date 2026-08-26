from __future__ import annotations

from dataclasses import dataclass


# El estado sólo describe la caja de identidad operacional. El nombre de contexto es opcional
# mientras la aplicación bootstrap todavía no tenga una Tool Configuration proyectada.
@dataclass(frozen=True, slots=True)
class OperationalBrandState:
    context_name: str | None = None
    assistant_label: str = 'Asistente de Decisiones Ágiles'
    logo_src: str | None = None
    logo_alt: str = 'ADA'

    def __post_init__(self) -> None:
        object.__setattr__(self, 'context_name', _optional_text(self.context_name, 'context_name'))
        object.__setattr__(self, 'assistant_label', _text(self.assistant_label, 'assistant_label'))
        object.__setattr__(self, 'logo_alt', _text(self.logo_alt, 'logo_alt'))
        if self.logo_src is not None:
            object.__setattr__(self, 'logo_src', _text(self.logo_src, 'logo_src'))


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Operational brand {field_name} cannot be empty')
    return value.strip()


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)
