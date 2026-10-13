# Catálogo vacío por defecto: no inventar fuentes que la herramienta no declaró.
from __future__ import annotations

from .bindings import DashboardTimeStatusSourceBinding

INTEGRATED_OPERATIONS_TIME_STATUS_SOURCES: tuple[DashboardTimeStatusSourceBinding, ...] = ()
