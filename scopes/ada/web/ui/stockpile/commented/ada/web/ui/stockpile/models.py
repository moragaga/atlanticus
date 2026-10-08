from __future__ import annotations

# Los modelos aceptan estados DisplayValue ya normalizados, sin convertir sus textos al construirlos.

from dataclasses import dataclass
from math import isfinite

from ada.web.ui.display_status import DisplayValue


# Se validan únicamente clases opcionales; el contenido visual no se condiciona por clases.
def _optional_class(value: str | None, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f'{name} must be null or a non-empty string')


@dataclass(frozen=True, slots=True)
# Una pila conserva identificador y label del consumidor y dos lecturas independientes.
class StockpileItem:
    key: str
    label: str
    percentage: DisplayValue
    height_m: DisplayValue

    # Estas invariantes evitan identidades duplicadas, tipos incompatibles y escalas inválidas.
    def __post_init__(self) -> None:
        for name in ('key', 'label'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Stockpile {name} must be a non-empty string')
            object.__setattr__(self, name, value.strip())
        for name in ('percentage', 'height_m'):
            if not isinstance(getattr(self, name), DisplayValue):
                raise TypeError(f'Stockpile {name} must be DisplayValue')


@dataclass(frozen=True, slots=True)
# La escala es una decisión de composición. No asumimos 28 ni 30 metros por defecto.
class StockpilePanel:
    items: tuple[StockpileItem, ...]
    scale_max_m: float
    class_name: str | None = None
    item_class_name: str | None = None
    graphic_class_name: str | None = None
    label_class_name: str | None = None
    value_class_name: str | None = None

    # Estas invariantes evitan identidades duplicadas, tipos incompatibles y escalas inválidas.
    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not self.items:
            raise ValueError('Stockpile items must be a non-empty tuple')
        if any(not isinstance(item, StockpileItem) for item in self.items):
            raise TypeError('Stockpile items must contain StockpileItem values')
        keys = [item.key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError('Stockpile item keys must be unique')
        if (
            isinstance(self.scale_max_m, bool)
            or not isinstance(self.scale_max_m, int | float)
            or not isfinite(self.scale_max_m)
            or self.scale_max_m <= 0
        ):
            raise ValueError('Stockpile visual scale must be finite and greater than zero')
        for name in (
            'class_name',
            'item_class_name',
            'graphic_class_name',
            'label_class_name',
            'value_class_name',
        ):
            _optional_class(getattr(self, name), name)
